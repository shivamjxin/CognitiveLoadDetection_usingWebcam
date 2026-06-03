import cv2
import numpy as np
import math

# Order: Nose Tip, Nose Bridge, Left Eye Outer, Left Eye Inner, Right Eye Inner, Right Eye Outer
FACE_3D_MODEL = np.array([
    [0.0, 0.0, 0.0],             
    [0.0, -30.0, -15.0],         
    [-45.0, -20.0, -25.0],       
    [-20.0, -20.0, -20.0],       
    [20.0, -20.0, -20.0],        
    [45.0, -20.0, -25.0]
], dtype=np.float64)

# MediaPipe anchor indices that correspond to the 3D model above
ANCHOR_INDICES = [1, 168, 33, 133, 362, 263]


def normalize_head_pose(face_landmarks, frame_width, frame_height):
    """
    Calculates the pitch, yaw, and roll of the head, and mathematically
    cancels out the head movement to isolate pure eye coordinates.
    """
    # Intrinsic Camera Matrix based on current frame size
    focal_length = frame_width
    center_x = frame_width / 2
    center_y = frame_height / 2
    
    camera_matrix = np.array([
        [focal_length, 0, center_x],
        [0, focal_length, center_y],
        [0, 0, 1]
    ], dtype=np.float64)

    # Distance Coefficients assuming no distortion
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    # Extract the 2D anchor pixels from the current frame
    #face_landmark contains 468 points on face and 10 points for iris since explicitly set
    #storing all of the og 2d landmarks for now (later if need be RESTRICT to SAVE BANDWIDTH)
    # used in ml pipeline etc to detect blink, calculate EAR etc
    image_points_denormalized = []
    for index in ANCHOR_INDICES:
        landmark = face_landmarks.landmark[index]
        x_pixel = int(landmark.x * frame_width)
        y_pixel = int(landmark.y * frame_height)
        image_points_denormalized.append([x_pixel, y_pixel])

    image_points = np.array(image_points_denormalized, dtype=np.float64)

    # Run the PnP Calculus
    success_pnp, rotation_vector, translation_vector = cv2.solvePnP(
        FACE_3D_MODEL, 
        image_points, 
        camera_matrix, 
        dist_coeffs
    )

    if not success_pnp:
        # Failsafe if the math fails
        return {"pitch": 0, "yaw": 0, "roll": 0}, {"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0}

    # Extract Pitch, Yaw, Roll
    rmat, _ = cv2.Rodrigues(rotation_vector)   # convert the calculus vector into 3x3 rotation matrix
    angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)  # decompose matrix into human-readable format
    pitch, yaw, roll = angles[0], angles[1], angles[2]

    pose_data = {
        "pitch": float(pitch),
        "yaw": float(yaw),
        "roll": float(roll)
    }

    # Pose Normalization
    rmat_inverse = np.linalg.inv(rmat)   # inverse rotation matrix

    # getting 3d coords for left iris center with index: 468 and right iris center (473)  
    # since we are applying the inverse rotation to only the eyes for now
    left_iris = face_landmarks.landmark[468]
    right_iris = face_landmarks.landmark[473]

    # denormalizing the coords and creating a 3x1 vector
    left_eye_vec = np.array([[left_iris.x * frame_width], [left_iris.y * frame_height], [left_iris.z * frame_width]])
    right_eye_vec = np.array([[right_iris.x * frame_width], [right_iris.y * frame_height], [right_iris.z * frame_width]])

    # Center the eyes (Cancel Translation)
    left_eye_centered = left_eye_vec - translation_vector
    right_eye_centered = right_eye_vec - translation_vector

    # Un-tilt the eyes (Cancel Rotation)
    left_eye_normalized = rmat_inverse.dot(left_eye_centered)
    right_eye_normalized = rmat_inverse.dot(right_eye_centered)

    normalized_eyes = {
        "left_x": float(left_eye_normalized[0][0]), "left_y": float(left_eye_normalized[1][0]),
        "right_x": float(right_eye_normalized[0][0]), "right_y": float(right_eye_normalized[1][0])
    }

    return pose_data, normalized_eyes


def calculate_ear(face_landmarks, frame_width, frame_height):
    """
    Calculates the Eye Aspect Ratio (EAR) to detect blinks and eye aperture.
    Includes the epsilon fix to prevent division by zero crashes.
    """
    def compute_distance(p1, p2):
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
    
    def get_pixel(idx):
        lm = face_landmarks.landmark[idx]
        return [lm.x * frame_width, lm.y * frame_height]

    # MediaPipe Left Eye Indices (Outer, Top1, Top2, Inner, Bottom1, Bottom2)
    left_eye_pts = [33, 160, 158, 133, 153, 144]
    # MediaPipe Right Eye Indices
    right_eye_pts = [362, 385, 387, 263, 373, 380]

    # Process Left Eye
    p1, p2, p3, p4, p5, p6 = [get_pixel(i) for i in left_eye_pts]
    left_vertical_1 = compute_distance(p2, p6)
    left_vertical_2 = compute_distance(p3, p5)
    left_horizontal = compute_distance(p1, p4)
    left_ear = (left_vertical_1 + left_vertical_2) / (2.0 * left_horizontal + 1e-6) # 1e-6 prevents zero-division crash

    # Process Right Eye
    p1, p2, p3, p4, p5, p6 = [get_pixel(i) for i in right_eye_pts]
    right_vertical_1 = compute_distance(p2, p6)
    right_vertical_2 = compute_distance(p3, p5)
    right_horizontal = compute_distance(p1, p4)
    right_ear = (right_vertical_1 + right_vertical_2) / (2.0 * right_horizontal + 1e-6)

    # Return Average EAR
    return (left_ear + right_ear) / 2.0