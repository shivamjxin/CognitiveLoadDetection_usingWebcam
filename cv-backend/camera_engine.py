import cv2
import mediapipe as mp
import time
import json
import spatial_math

# Force optimal parameters for MediaPipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    static_image_mode=False,
    refine_landmarks=True, # by default MediaPipe face mesh tracks 468 points on face, keeping it True gives us hyper-accurate data around the eyes to calculate EAR => to track fine iris movements
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Initialize OpenCV WebCam w/ Hardcoded parameters for a steady 720p HD stream
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

# Variables for FPS calculation
pTime = 0
frame_id = 0  # counter for packet indexing to make debugging easier

# Grab the exact moment the script starts
script_start_time = time.time()

print("System booting... Camera Engine Online. Press 'q' to quit.")

# Crash-Proof Data Pipeline
with open("../data_logs/cv_stream.jsonl", "a") as cv_log_file:
    
    while cap.isOpened():
        # grab UNIX epoch timestamp the moment loop starts and then find time relative to start
        current_time = time.time()
        relative_time_sec = current_time - script_start_time 
        epoch_time_ms = int(current_time * 1000)

        success, frame = cap.read()
        if not success:
            print("Ignoring failed frame.")
            continue
        
        frame_id += 1

        # Memory optimization for MediaPipe
        frame.flags.writeable = False   #  making the array const to avoid changes to be made and not creating a copy rather passing frame by reference to Mediapipe (cpp)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)   # openCV image read as BGR need to convert to RGB for the neural net

        results = face_mesh.process(frame_rgb)   # run the neural network and map the 468 points onto frame_rgb

        frame.flags.writeable = True   # changing back to mutable format to allow for drawing of landmarks
        frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)   # Revert to BGR for openCV

        # Initialize the clean packet for this frame
        raw_frame_packet = {
            "frame_id": frame_id,
            "epoch_time_ms": epoch_time_ms,
            "relative_time_sec": round(relative_time_sec, 4),
            "no_face": True,
            "head_pose": None,
            "head_normalized_eyes": None,
            "ear": None
        }

        # perform calculations if face is found
        if results.multi_face_landmarks:
            raw_frame_packet["no_face"] = False
            
            for face_landmarks in results.multi_face_landmarks:
                frame_height, frame_width, _ = frame.shape
                
                # Get the Head Pose & Normalized Eyes
                pose_data, normalized_eyes = spatial_math.normalize_head_pose(
                    face_landmarks, 
                    frame_width, 
                    frame_height
                )
                
                # Get the Blink Data (EAR)
                avg_ear = spatial_math.calculate_ear(
                    face_landmarks, 
                    frame_width, 
                    frame_height
                )

                # getting gaze data
                gaze_data = spatial_math.calculate_gaze_ratios(face_landmarks, frame_width, frame_height)
                
                # Package it up
                raw_frame_packet["head_pose"] = pose_data
                raw_frame_packet["head_normalized_eyes"] = normalized_eyes
                raw_frame_packet["ear"] = avg_ear
                raw_frame_packet["gaze_ratios"] = gaze_data
                
                # Display metrics on screen so you know it's working
                cv2.putText(frame, f"Pitch: {int(pose_data['pitch'])}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"Yaw: {int(pose_data['yaw'])}", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"EAR: {round(avg_ear, 3)}", (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"Gaze H: {gaze_data['horizontal_ratio']}", (20, 230), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                cv2.putText(frame, f"Gaze V: {gaze_data['vertical_ratio']}", (20, 270), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)

        # Write data immediately to hard drive
        cv_log_file.write(json.dumps(raw_frame_packet) + "\n")
        
        # Calculate & Display FPS
        cTime = time.time()
        fps = 1 / (cTime - pTime) if (cTime - pTime) > 0 else 0
        pTime = cTime
        cv2.putText(frame, f'FPS: {int(fps)}', (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)

        cv2.imshow('Cognitive Load Webcam Engine', frame)

        # Hit 'q' to break the loop safely
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()