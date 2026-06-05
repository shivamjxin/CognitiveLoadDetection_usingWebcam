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
        x_pixel = float(landmark.x * frame_width)
        y_pixel = float(landmark.y * frame_height)
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
        # Using a standard 600mm (60cm) depth baseline to prevent coordinate collapse
        return {"pitch": 0, "yaw": 0, "roll": 0}, np.eye(3), np.array([[0], [0], [600.0]], dtype=np.float64)

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

    return pose_data, rmat_inverse, translation_vector

def get_normalized_landmarks(face_landmarks, rmat_inverse, translation_vector, frame_width, frame_height):
    """
    Transforms the subset of landmarks required for our features into the 
    head-pose-invariant 3D canonical coordinate space.
    """
    # Combined collection of all indices used across EAR, Gaze, and Mouth features
    needed_indices = [
        33, 160, 158, 133, 153, 144, 159, 145, 468,  # Left Eye & Iris (for EAR + Vertical Gaze + Iris)
        362, 385, 387, 263, 373, 380, 473,           # Right Eye & Iris (for EAR + Iris) since vertical gaze calcuate only using left eye because of symmetry  
        61, 291, 13, 14, 1                              # Mouth corners and Lip borders + Nose Tip as spatial origin points
    ]
    
    focal_length = frame_width
    center_x = frame_width / 2
    center_y = frame_height / 2
    
    # Calculate a metric scaling factor using the eye anchors to transform normalized depth (z) to mm
    lm_left_eye = face_landmarks.landmark[33]
    lm_right_eye = face_landmarks.landmark[263]
    norm_width = math.sqrt((lm_right_eye.x - lm_left_eye.x)**2 + (lm_right_eye.y - lm_left_eye.y)**2)
    face_scale_mm = 90.0 / (norm_width + 1e-6)  # 90mm is the strict distance between corners in FACE_3D_MODEL
    
    Z_face = translation_vector[2][0]
    normalized_dict = {}
    
    for idx in needed_indices:
        lm = face_landmarks.landmark[idx]
        
        # Determine absolute metric depth in millimeters
        Z_mm = Z_face + (lm.z * face_scale_mm)
        
        # Reverse pinhole projection to map screen pixels to true metric camera space (mm)
        X_pixel = lm.x * frame_width
        Y_pixel = lm.y * frame_height
        
        X_mm = (X_pixel - center_x) * Z_mm / focal_length
        Y_mm = (Y_pixel - center_y) * Z_mm / focal_length
        
        P_camera = np.array([[X_mm], [Y_mm], [Z_mm]], dtype=np.float64)
        
        # Apply pose normalization (Un-translate then Un-rotate into canonical world space)
        P_normalized = rmat_inverse.dot(P_camera - translation_vector)
        
        normalized_dict[idx] = P_normalized.flatten()
        
    return normalized_dict


def calculate_ear(normalized_dict):
    """
    Calculates the scale-invariant Eye Aspect Ratio (EAR) to 
    detect blinks and eye aperture using unskewed 3D spatial boundaries
    Includes the epsilon fix to prevent division by zero crashes.
    """

    # MediaPipe Left Eye Indices (Outer, Top1, Top2, Inner, Bottom1, Bottom2)
    left_eye_pts = [33, 160, 158, 133, 153, 144]
    # MediaPipe Right Eye Indices
    right_eye_pts = [362, 385, 387, 263, 373, 380]

    # Process Left Normalized Eye
    p1, p2, p3, p4, p5, p6 = [normalized_dict[i] for i in left_eye_pts]
    left_vertical_1 = np.linalg.norm(p2 - p6)
    left_vertical_2 = np.linalg.norm(p3 - p5)
    left_horizontal = np.linalg.norm(p1 - p4)
    left_ear = (left_vertical_1 + left_vertical_2) / (2.0 * left_horizontal + 1e-6) # 1e-6 prevents zero-division crash and 2 since we take 2 vertical distances

    # Process Right Normalized Eye
    p1, p2, p3, p4, p5, p6 = [normalized_dict[i] for i in right_eye_pts]
    right_vertical_1 = np.linalg.norm(p2 - p6)
    right_vertical_2 = np.linalg.norm(p3 - p5)
    right_horizontal = np.linalg.norm(p1 - p4)
    right_ear = (right_vertical_1 + right_vertical_2) / (2.0 * right_horizontal + 1e-6)

    # Return Average EAR with force typecasting to avoid JSON serialization crahses
    return float((left_ear + right_ear) / 2.0)

def calculate_gaze_ratios(normalized_dict):
    """
    Computes precise coordinate-based horizontal and vertical look distributions 
    relative to the orbital walls using head-stabilized 3D points.
    """

    # Left Eye Points: Outer Corner (33), Inner Corner (133), Iris Center (468)
    left_outer = normalized_dict[33]
    left_inner = normalized_dict[133]
    left_iris  = normalized_dict[468]

    # Right Eye Points: Inner Corner (362), Outer Corner (263), Iris Center (473)
    right_inner = normalized_dict[362]
    right_outer = normalized_dict[263]
    right_iris  = normalized_dict[473]
    # left-eye horizontal ratio
    # Calculate distance from outer corner to iris, and total width of eye socket
    left_dist_out = np.linalg.norm(left_iris - left_outer)
    left_total_width = np.linalg.norm(left_inner - left_outer) + 1e-6
    left_h_ratio = left_dist_out / left_total_width

    # right eye horizontal ratio
    right_dist_in = np.linalg.norm(right_iris - right_inner)
    right_total_width = np.linalg.norm(right_outer - right_inner) + 1e-6
    right_h_ratio = right_dist_in / right_total_width

    # Average the horizontal ratios (0.5 means dead center, < 0.5 looking right, > 0.5 looking left)
    avg_h_gaze = (left_h_ratio + right_h_ratio) / 2.0

    # VERTICAL RATIO
    # Top lid center (159), Bottom lid center (145), Iris center (468)
    left_top = normalized_dict[159]
    left_bottom = normalized_dict[145]
    left_v_dist = np.linalg.norm(left_iris - left_top)
    left_total_height = np.linalg.norm(left_bottom - left_top) + 1e-6
    avg_v_gaze = left_v_dist / left_total_height

    # only calculating gaze on left eye since we cant look up from one eye and down from other 

    return {
        "horizontal_ratio": round(float(avg_h_gaze), 4),
        "vertical_ratio": round(float(avg_v_gaze), 4)
    } 

def calculate_mouth_metrics(normalized_dict):
    """
    Extracts raw unskewed 3D distances for the mouth corners (AU14 ingredient) 
    and inner lips margins (AU24 ingredient) from the stabilized facial surface.
    """
    mouth_left = normalized_dict[61]
    mouth_right = normalized_dict[291]
    lip_upper = normalized_dict[13]
    lip_lower = normalized_dict[14]

    # STABLE DENOMINATOR: Rigid distance between outer eye corners
    eye_stable_width = np.linalg.norm(normalized_dict[33] - normalized_dict[263]) + 1e-6
    
    # Convert absolute measurements into scale-invariant ratios
    mouth_width_ratio = np.linalg.norm(mouth_left - mouth_right) / eye_stable_width
    lip_gap_ratio = np.linalg.norm(lip_upper - lip_lower) / eye_stable_width

    return {
        "mouth_width_raw": round(float(mouth_width_ratio), 4),
        "lip_gap_raw": round(float(lip_gap_ratio), 4)
    }