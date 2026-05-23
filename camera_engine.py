import cv2
import mediapipe as mp
import time


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

print("Starting Camera press 'q' to quit.")

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
    
            mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=mp_face_mesh.FACEMESH_TESSELATION,  # tells how to draw connections between the points
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
            )
            
            mp_drawing.draw_landmarks(
                image=frame,
                landmark_list=face_landmarks,
                connections=mp_face_mesh.FACEMESH_IRISES,   # targets the iris for drawing
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_iris_connections_style()
            )

            # note: This is where we will eventually extract the raw points
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