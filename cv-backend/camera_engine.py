import cv2
import mediapipe as mp
import time
import numpy as np
import json
import socketio


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
frame_id = 0  # counter for packet indexing to make debugging easier

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

# client initialzation
sio = socketio.Client()
try:
    sio.connect('http://localhost:5000')  # setting up connection to local webhost
    is_connected = True
except:
    print("server is offline")
    is_connected = False        # to be changed to create a strict dependency later

while cap.isOpened():

    # grab UNIX epoch timestamp the moment loop starts
    start_time_ms = int(time.time()*1000)

    success, frame = cap.read()
    if not success:
        print("Ignoring failed frame.")
        continue

    frame_id += 1

    # intialize packets for this frame
    raw_frame_packet = {
        "frame_id": frame_id,
        "start_time_ms": start_time_ms,
        "no_face": True,
        "head_pose": None,
        "head_normalized_eyes": None,
        "original_2d_landmarks": None

    }

    frame.flags.writeable = False  #  making the array const to avoid changes to be made and not creating a copy rather passing frame by reference to Mediapipe (cpp)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # openCV image read as BGR need to convert to RGB for the neural net
    
    results = face_mesh.process(frame_rgb)  # run the neural network and map the 468 points onto frame_rgb

    frame.flags.writeable = True  # changing back to mutable format to allow for drawing of landmarks
    frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)  # Revert to BGR for openCV


    if results.multi_face_landmarks:  # checking for face

        raw_frame_packet["no_face"] = False

        for face_landmarks in results.multi_face_landmarks:  # face_landmark contains 468 points on face and 10 points for iris since explicitly set

            # storing all of the og 2d landmarks for now (later if need be RESTRICT to SAVE BANDWIDTH)
            # used in ml pipeline etc to detect blink, calculate EAR etc
            raw_landmarks_2d = [{"x": lm.x, "y": lm.y} for lm in face_landmarks.landmark]
            raw_frame_packet["original_2d_landmarks"] = raw_landmarks_2d

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
            success_pnp, rotation_vector, translation_vector = cv2.solvePnP(
                face_3d_model, 
                image_points, 
                camera_matrix, 
                dist_coeffs
            )

            if success_pnp:
                # Convert the calculus vector into a 3x3 Rotation Matrix
                rmat, _ = cv2.Rodrigues(rotation_vector)
                
                # Decompose the Matrix into human-readable degrees
                angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
                
                pitch, yaw, roll = angles[0], angles[1], angles[2]

                raw_frame_packet["head_pose"] = {
                                                "pitch": pitch,
                                                 "yaw": yaw,
                                                 "roll": roll
                                                 }
                
                # Display the real-time angles on the screen!
                cv2.putText(frame, f'Pitch: {int(pitch)}', (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f'Yaw:   {int(yaw)}', (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f'Roll:  {int(roll)}', (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

                # HEAD POSE NORM
                rmat_inverse = np.linalg.inv(rmat)  # inverse rot matrix needed to unskew the face

                # getting 3d coords for left iris center with inex: 468 and right iris center (473)   
                # since we are applying the inverse rotation to only the eyes for now
                left_iris = face_landmarks.landmark[468]
                right_iris = face_landmarks.landmark[473]

                # de-normalizing the coords and creating a 3x1 vector
                left_eye_vec = np.array([[left_iris.x * frame_width], [left_iris.y * frame_height], [left_iris.z * frame_width]])
                right_eye_vec = np.array([[right_iris.x * frame_width], [right_iris.y * frame_height], [right_iris.z * frame_width]])

                # rotating the eyes back to dead center or frontal position or performing pose normalization
                left_eye_normalized = rmat_inverse.dot(left_eye_vec)
                right_eye_normalized = rmat_inverse.dot(right_eye_vec)

                raw_frame_packet["head_normalized_eyes"] = {
                    "left_x": float(left_eye_normalized[0][0]), "left_y": float(left_eye_normalized[1][0]),
                    "right_x": float(right_eye_normalized[0][0]), "right_y": float(right_eye_normalized[1][0])
                }
    
    #print(json.dumps(raw_frame_packet))
    if is_connected:
        sio.emit('cv_frame',raw_frame_packet)  # work as transmitter to send data to the server


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