import cv2
import mediapipe as mp
import mediapipe.python.solutions.face_mesh as mp_face_mesh
import time
from pylsl import StreamInfo, StreamOutlet
import spatial_math

# Force optimal parameters for MediaPipe
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

print("Initializing LSL Stream...")
cv_info = StreamInfo(
    'WebcamFaceMetrics', 
    'Biometrics', 
    13,                     # 12 metrics + 1 tracking flag
    30,                    # Target FPS
    'float32', 
    'mit_cv_backend_001'
)
cv_outlet = StreamOutlet(cv_info)

# Grab the exact moment the script starts
script_start_time = time.time()

print("System booting... Camera Engine Online. Press 'q' to quit.")


    
while cap.isOpened():

    success, frame = cap.read()
    if not success:
        print("Ignoring failed frame.")
        continue

    # Memory optimization for MediaPipe
    frame.flags.writeable = False   #  making the array const to avoid changes to be made and not creating a copy rather passing frame by reference to Mediapipe (cpp)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)   # openCV image read as BGR need to convert to RGB for the neural net

    results = face_mesh.process(frame_rgb)   # run the neural network and map the 468 points onto frame_rgb

    frame.flags.writeable = True   # changing back to mutable format to allow for drawing of landmarks
    frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)   # Revert to BGR for openCV

    # perform calculations if face is found
    if results.multi_face_landmarks:
        
        for face_landmarks in results.multi_face_landmarks:
            frame_height, frame_width, _ = frame.shape
            
            # Get the Head Pose, rmat-inv and translation-vec for scale-invariant calculations  
            pose_data, rmat_inverse, translation_vector = spatial_math.normalize_head_pose(
                face_landmarks, 
                frame_width, 
                frame_height
            )

            # extract unified normalized 3D landmarks for an unskewed face
            normalized_dict = spatial_math.get_normalized_landmarks(
                face_landmarks,
                rmat_inverse,
                translation_vector,
                frame_width,
                frame_height
            )

            # reconstructing normalized eye anchors for telemetry packet matching 
            normalized_eyes = {
                "left_x": float(normalized_dict[468][0]), "left_y": float(normalized_dict[468][1]),
                "right_x": float(normalized_dict[473][0]), "right_y": float(normalized_dict[473][1])
            }
            
            # Getting gemoteric normalized features
            avg_ear = spatial_math.calculate_ear(normalized_dict)
            gaze_data = spatial_math.calculate_gaze_ratios(normalized_dict)
            mouth_data = spatial_math.calculate_mouth_metrics(normalized_dict)
            
            # Package the 7-element float array
            # Order: 
            # 0:Tracking_Flag, 1:Pitch, 2:Yaw, 3:Roll, 4:EAR, 
            # 5:Gaze_H, 6:Gaze_V, 7:Mouth_W, 8:Lip_Gap,
            # 9:Left_Iris_X, 10:Left_Iris_Y, 11:Right_Iris_X, 12:Right_Iris_Y
            
            spatial_data = [
                1.0,  # Tracking Flag: 1.0 means valid face
                float(pose_data['pitch']),
                float(pose_data['yaw']),
                float(pose_data['roll']),
                float(avg_ear),
                float(gaze_data['horizontal_ratio']),
                float(gaze_data['vertical_ratio']),
                float(mouth_data['mouth_width_raw']),
                float(mouth_data['lip_gap_raw']),
                float(normalized_eyes['left_x']),
                float(normalized_eyes['left_y']),
                float(normalized_eyes['right_x']),
                float(normalized_eyes['right_y'])
            ]
            
            # Push array directly to local memory stream
            cv_outlet.push_sample(spatial_data)

            # Display metrics on screen so you know it's working
            cv2.putText(frame, f"Pitch: {int(pose_data['pitch'])}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(frame, f"Yaw: {int(pose_data['yaw'])}", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(frame, f"EAR: {round(avg_ear, 3)}", (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(frame, f"Gaze H: {gaze_data['horizontal_ratio']}", (20, 230), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
            cv2.putText(frame, f"Gaze V: {gaze_data['vertical_ratio']}", (20, 260), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
            cv2.putText(frame, f"Mouth W: {mouth_data['mouth_width_raw']}", (20, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    else:
        # FACE LOST LOGIC
        # Push 13-element float array of zeros with 0.0 tracking flag
        spatial_data = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        cv_outlet.push_sample(spatial_data)
    
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