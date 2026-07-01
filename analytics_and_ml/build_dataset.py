import pyxdf
import pandas as pd
import numpy as np
import os
import glob
import json

# PIPELINE CONFIG
CV_STREAM_NAME = 'WebcamFaceMetrics' 
GAME_STREAM_NAME = 'PygameGameEvents'

def extract_and_sync_xdf(xdf_file_path):
    """
    Open a single .xdf file, extracts the 30Hz CV and 60Hz Game streams,
    and merges them using a backward-looking timestamp alignment to prevent data leakage.
    """
    # Extract filename to use as a unique identifier for this specific user/session
    session_id = os.path.basename(xdf_file_path).replace('.xdf', '')
    print(f"[{session_id}] Extracting streams...")

    try:
        data, header = pyxdf.load_xdf(xdf_file_path)
    except Exception as e:
        print(f"[{session_id}] ERROR: Failed to load .xdf. File might be corrupted. ({e})")
        return None

    cv_stream, pygame_stream = None, None

    # Isolate our two target streams from the LSL recording
    for stream in data:
        stream_name = stream['info']['name'][0]
        if stream_name == CV_STREAM_NAME:
            cv_stream = stream
        elif stream_name == GAME_STREAM_NAME:
            pygame_stream = stream

    if not cv_stream or not pygame_stream:
        print(f"[{session_id}] ERROR: Missing required LSL streams. Skipping file.")
        return None

    # We use LSL's internal 'time_stamps' array to guarantee microsecond network sync
    # Map the 13 specific OpenCV variables
    cv_columns = [
        'Tracking_Flag', 'Pitch', 'Yaw', 'Roll', 'EAR', 
        'Gaze_H', 'Gaze_V', 'Mouth_W', 'Lip_Gap',
        'Left_Iris_X', 'Left_Iris_Y', 'Right_Iris_X', 'Right_Iris_Y'
    ]
    df_cv = pd.DataFrame(cv_stream['time_series'], columns=cv_columns)
    df_cv['timestamp'] = cv_stream['time_stamps']

    # Unpack the JSON strings sent by Pygame
    game_data = []
    for val in pygame_stream['time_series']:
        try:
            # Parse the JSON string payload
            packet = json.loads(val[0])  # val[0] since everything is stored in a json enclosed in list with shape(1,)
        except Exception:
            # Fallback if somehow a flat string gets through
            packet = {'state_id': val[0]}
        game_data.append(packet)

    df_game = pd.DataFrame(game_data)
    df_game['timestamp'] = pygame_stream['time_stamps']
    
    # Rename state_id to FSM_State so we don't break the Purge logic below
    if 'state_id' in df_game.columns:
        df_game.rename(columns={'state_id': 'FSM_State'}, inplace=True)


    # pandas asofmerge does binary search for which chronological order is required
    df_cv = df_cv.sort_values('timestamp')
    df_game = df_game.sort_values('timestamp')

    # drop events that occur at the same time keeping the last thing like switching from one state to another
    df_game = df_game.drop_duplicates(subset=['timestamp'], keep='last')

    # Snap the FSM state to the camera frame looking strictly backward.
    # This ensures a frame is only labeled "Stressed" if the stressor happened before the frame was captured.
    df_merged = pd.merge_asof(
        df_cv,
        df_game,
        on='timestamp',
        direction='backward'
    )
    
    # Forward-fill ALL the unpacked game states (not just FSM_State) so every camera frame has the full context
    game_cols = df_game.columns.drop('timestamp')
    df_merged[game_cols] = df_merged[game_cols].ffill()

    df_merged = df_merged.dropna(subset=['FSM_State'])

    # Apply the mask to purge the transitional noise
    df_clean = df_merged.copy()
    
    # Attach the session ID so we can group by user later in the ML pipeline
    df_clean['Session_ID'] = session_id

    # using relative timing with each session starting at 0.0
    first_timestamp = df_clean['timestamp'].iloc[0]
    df_clean['Relative_Time_Sec'] = df_clean['timestamp'] - first_timestamp

    print(f"[{session_id}] Success. Synced {len(df_clean)} frames.")
    return df_clean

def build_dataset(input_dir, output_filepath):
    """
    Crawls the input directory for all .xdf files, processes them, 
    and concatenates them into a single master Parquet dataset.
    """
    search_pattern = os.path.join(input_dir, '*.xdf')
    xdf_files = glob.glob(search_pattern)
    
    if not xdf_files:
        print(f"CRITICAL WARNING: No .xdf files found in {input_dir}. Ensure your pathing is correct.")
        return

    print(f"Found {len(xdf_files)} experiment files. Beginning batch processing...\n")
    
    all_sessions = []
    
    for file_path in xdf_files:
        session_df = extract_and_sync_xdf(file_path)
        if session_df is not None and not session_df.empty:
            all_sessions.append(session_df)

    if all_sessions:
        # Stack all individual sessions on top of each other
        master_df = pd.concat(all_sessions, ignore_index=True)
        
        # Create the output directory if it doesn't exist (e.g., data_logs/processed)
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        
        # Export as Parquet
        master_df.to_parquet(output_filepath, index=False)
        print(f"\n Dataset saved to {output_filepath}")
        print(f"Total Combined Frames: {len(master_df)}")
    else:
        print("\nFAILED. No valid data extracted from the provided XDF files.")

def build_csv_dataset(input_dir, output_filepath):
    """
    Crawls the input directory for all static .csv files (e.g., NASA-TLX survey scores),
    injects the source file name as a 'Session_ID' tag to ensure cross-compatibility 
    with the .xdf telemetry, and fuses them into a single analytical CSV dataset.
    """
    search_pattern = os.path.join(input_dir, '*.csv')
    csv_files = glob.glob(search_pattern)
    
    if not csv_files:
        print(f"WARNING: No .csv files found in {input_dir}. Skipping tabular data processing.")
        return

    print(f"\nFound {len(csv_files)} CSV files. Beginning merge sequence...")
    
    all_csv_data = []
    
    for file_path in csv_files:
        # Extract filename for session_id
        session_tag = os.path.basename(file_path).replace('.csv', '')
        
        try:
            # Read the individual subject's CSV file
            df = pd.read_csv(file_path)
            
            # Inject the Session_ID tag so we can map this survey back to their facial data
            # Insert it as the very first column for clean readability
            df.insert(0, 'Session_ID', session_tag)
            
            all_csv_data.append(df)
            print(f"[{session_tag}] CSV data successfully loaded and tagged.")
        except Exception as e:
            print(f"[{session_tag}] ERROR: Failed to read CSV. ({e})")
            
    if all_csv_data:
        # Stack all individual CSV datasets into one continuous dataframe
        master_csv_df = pd.concat(all_csv_data, ignore_index=True)
        
        # Create the output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        
        # Export the unified CSV
        master_csv_df.to_csv(output_filepath, index=False)
        print(f"\n CSV dataset saved to {output_filepath}")
        print(f"Total Combined CSV Rows: {len(master_csv_df)}")
    else:
        print("\n FAILED. No valid data extracted from the provided CSV files.")

if __name__ == "__main__":
    # PATH SETUP 
    # Adjust these relative paths based on where this script lives in your project structure.
    
    INPUT_DIRECTORY = "../data_logs" 
    
    # Target files
    OUTPUT_PARQUET_FILE = "../data_logs/processed/clean_dataset.parquet"
    OUTPUT_CSV_FILE = "../data_logs/processed/survey_data.csv"
    
    # Process the 30Hz high-frequency XDF telemetry
    print("-- Forming telemetry dataset --")
    build_dataset(INPUT_DIRECTORY, OUTPUT_PARQUET_FILE)
    
    print("\n" + "="*50 + "\n")
    
    # Process the tabular survey/metadata CSVs
    print("-- forming survey dataset --")
    build_csv_dataset(INPUT_DIRECTORY, OUTPUT_CSV_FILE)