import cv2
import mediapipe as mp
import time
import numpy as np


mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Force optimal parameters to maximize computational efficiency
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    static_image_mode=False,
    refine_landmarks=True, # by default MediaPipe face mesh tracks 468 points on face, keeping it True gives us hyper-accurate data around the eyes to calculate EAR => to track fine iris movements
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)


cap = cv2.VideoCapture(0)

# Hardcoded parameters for a steady 720p HD stream
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

# Variables for FPS calculation
pTime = 0

#print("Starting Camera press 'q' to quit.")

# Order: Nose Tip, Nose Bridge, Left Eye Outer, Left Eye Inner, Right Eye Inner, Right Eye Outer
face_3d_model = np.array([
    [0.0, 0.0, 0.0],             
    [0.0, -30.0, -15.0],         
    [-45.0, -20.0, -25.0],       
    [-20.0, -20.0, -20.0],       
    [20.0, -20.0, -20.0],        
    [45.0, -20.0, -25.0]
], dtype = np.float64)

# camera intrinsic matrix
focal_length = 1280 
center_x = 1280 / 2
center_y = 720 / 2

camera_matrix = np.array([
    [focal_length, 0, center_x],
    [0, focal_length, center_y],
    [0, 0, 1]
], dtype=np.float64)

# Distance Coefficients assuming no distortion
dist_coeffs = np.zeros((4, 1), dtype=np.float64)

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("Ignoring failed frame.")
        continue

    frame.flags.writeable = False  #  making the array const to avoid changes to be made and not creating a copy rather passing frame by reference to Mediapipe (cpp)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # openCV image read as BGR need to convert to RGB for the neural net
    
    results = face_mesh.process(frame_rgb)  # run the neural network and map the 468 points onto frame_rgb

    frame.flags.writeable = True  # changing back to mutable format to allow for drawing of landmarks
    frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)  # Revert to BGR for openCV


    if results.multi_face_landmarks:  # checking for face
        for face_landmarks in results.multi_face_landmarks:  # face_landmark contains 468 points on face and 10 points for iris since explicitly set

            # 6 anchors points for head-pose normalization namely Nose Tip, Nose Bridge, Left Eye Outer, Left Eye Inner, Right Eye Inner, Right Eye Outer
            anchor_indices = [1, 168, 33, 133, 362, 263]
            image_points_denormalized = []

            frame_height, frame_width, _ = frame.shape

            for index in anchor_indices:
                landmark = face_landmarks.landmark[index]

                # denormalizing
                x_pixel = int(landmark.x * frame_width)
                y_pixel = int(landmark.y * frame_height)

                image_points_denormalized.append([x_pixel,y_pixel])

                # for visual check
                cv2.circle(frame, (x_pixel, y_pixel),4, (0,0,255), -1)

            image_points = np.array(image_points_denormalized, dtype=np.float64)  # since face_3d_model is a np.array and solvePnP requires similar dtypes

            # Run the PnP Math
            success, rotation_vector, translation_vector = cv2.solvePnP(
                face_3d_model, 
                image_points, 
                camera_matrix, 
                dist_coeffs
            )

            if success:
                # Convert the calculus vector into a 3x3 Rotation Matrix
                rmat, _ = cv2.Rodrigues(rotation_vector)
                
                # Decompose the Matrix into human-readable degrees
                angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
                
                pitch = angles[0]
                yaw = angles[1] 
                roll = angles[2]
                
                # Display the real-time angles on the screen!
                cv2.putText(frame, f'Pitch: {int(pitch)}', (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f'Yaw:   {int(yaw)}', (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f'Roll:  {int(roll)}', (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            # to build the `raw_frame_packet` for Person 3.

    # Calculate and display FPS to ensure we are hitting our 30Hz target
    cTime = time.time()
    fps = 1 / (cTime - pTime)
    pTime = cTime
    cv2.putText(frame, f'FPS: {int(fps)}', (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)


    cv2.imshow('Cognitive Load Webcam Engine', frame)

    # Break loop on pressing 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Cleanup
cap.release()
cv2.destroyAllWindows()