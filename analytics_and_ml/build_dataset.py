import pyxdf
import pandas as pd
import numpy as np
import os
import glob
import json

# PIPELINE CONFIG
CV_STREAM_NAME = 'WebcamFaceMetrics' 
GAME_STREAM_NAME = 'PygameGameEvents'

# The biological lag / orientation reflex buffer. 
TRANSITION_BUFFER_SEC = 1.0 

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

    # BUILD BASE TIMELINES 
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
            packet = json.loads(val[0])
        except Exception:
            # Fallback if somehow a flat string gets through
            packet = {'state_id': val[0]}
        game_data.append(packet)

    df_game = pd.DataFrame(game_data)
    df_game['timestamp'] = pygame_stream['time_stamps']
    
    # Rename state_id to FSM_State so we don't break the Purge logic below
    if 'state_id' in df_game.columns:
        df_game.rename(columns={'state_id': 'FSM_State'}, inplace=True)

    
    # Pandas requires strict chronological sorting before an ASOF merge
    df_cv = df_cv.sort_values('timestamp')
    df_game = df_game.sort_values('timestamp')

    df_game = df_game.drop_duplicates(subset=['timestamp'], keep='last')

    # Snap the FSM state to the camera frame looking strictly backward.
    # This ensures a frame is only labeled "Stressed" if the stressor happened BEFORE the frame was captured.
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

    #  BIOLOGICAL LAG DELETION and purging 1s 
    # We locate every exact moment the user's game state changed.
    state_changes = df_merged[df_merged['FSM_State'].shift() != df_merged['FSM_State']]
    
    keep_mask = pd.Series(True, index=df_merged.index)
    frames_dropped = 0

    for idx, row in state_changes.iterrows():
        # Skip the very first state initialization (usually just booting the app)
        if idx == df_merged.index[0]: 
            continue 
            
        change_time = row['timestamp']
        
        # Flag all camera frames that occurred within [0 to 1.0] seconds after the state changed
        drop_condition = (df_merged['timestamp'] >= change_time) & (df_merged['timestamp'] <= change_time + TRANSITION_BUFFER_SEC)
        keep_mask = keep_mask & ~drop_condition
        frames_dropped += drop_condition.sum()

    # Apply the mask to purge the transitional noise
    df_clean = df_merged[keep_mask].copy()
    
    # Attach the session ID so we can group by user later in the ML pipeline
    df_clean['Session_ID'] = session_id

    print(f"[{session_id}] Success. Synced {len(df_clean)} frames. Dropped {frames_dropped} transitional frames.")
    return df_clean

def build_master_dataset(input_dir, output_filepath):
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
        
        # Export as Parquet (Compresses heavily, preserves strict datatypes, loads in milliseconds)
        master_df.to_parquet(output_filepath, index=False)
        print(f"\n  Master dataset saved to {output_filepath}")
        print(f"Total Combined Frames: {len(master_df)}")
    else:
        print("\n FAILED. No valid data extracted from the provided files.")

if __name__ == "__main__":
    # PATH SETUP 
    # Adjust these relative paths based on where this script lives in your project structure.
    
    INPUT_DIRECTORY = "../data_logs" 
    OUTPUT_FILE = "../data_logs/processed/clean_dataset.parquet"
    
    build_master_dataset(INPUT_DIRECTORY, OUTPUT_FILE)