import json
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple
from fk_utils import compute_fk  # <-- you’ll implement this later


# === CONFIGURATION ===
CHECKERBOARD = (7, 5)  # inner corners (rows, cols)
SQUARE_SIZE = 0.036    # meters per square
CALIBRATION_DIR = Path("calibration_data")
POSES_FILE = CALIBRATION_DIR / "metadata.json"
OUTPUT_FILE = CALIBRATION_DIR / "T_camera2link4.json"


def load_pose_data(poses_file: Path):
    with open(poses_file, "r") as f:
        return json.load(f)


def detect_checkerboard_pose(image_path: Path, camera_matrix, dist_coeffs):
    """Detect checkerboard corners and estimate board pose wrt camera."""
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD)
    if not ret:
        print(f"[WARN] Checkerboard not found in {image_path.name}")
        return None

    # Refine corners
    corners = cv2.cornerSubPix(
        gray, corners, (11, 11), (-1, -1),
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1)
    )

    # Define world points (0,0,0) -> (cols-1, rows-1)
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[1], 0:CHECKERBOARD[0]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE

    # SolvePnP to get board pose in camera frame
    success, rvec, tvec = cv2.solvePnP(objp, corners, camera_matrix, dist_coeffs)
    if not success:
        return None

    R, _ = cv2.Rodrigues(rvec)
    T_target2camera = np.eye(4)
    T_target2camera[:3, :3] = R
    T_target2camera[:3, 3] = tvec[:, 0]
    return T_target2camera


def run_handeye_calibration():
    data = load_pose_data(POSES_FILE)

    # TODO: Load from your real camera calibration
    # For now, use placeholder intrinsics:
    fx, fy, cx, cy = 800, 800, 640, 480
    camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    dist_coeffs = np.zeros((5, 1))

    R_link4_2base, t_link4_2base = [], []
    R_target2camera, t_target2camera = [], []

    for entry in data:
        image_path = CALIBRATION_DIR / entry["image_path"]
        joint_positions = np.array(entry["joint_positions"])

        # Compute FK when ready (returns 4x4 transform)
        T_link4_2base = compute_fk(joint_positions)

        # Detect board pose
        T_target2camera = detect_checkerboard_pose(image_path, camera_matrix, dist_coeffs)
        if T_target2camera is None:
            continue

        # Extract rotation and translation components
        R_link4_2base.append(T_link4_2base[:3, :3])
        t_link4_2base.append(T_link4_2base[:3, 3])

        R_target2camera.append(T_target2camera[:3, :3])
        t_target2camera.append(T_target2camera[:3, 3])

    if len(R_target2camera) < 3:
        print("[ERROR] Not enough valid frames for calibration.")
        return

    # === Perform Hand-Eye Calibration ===
    R_cam2link4, t_cam2link4 = cv2.calibrateHandEye(
        R_link4_2base, t_link4_2base,
        R_target2camera, t_target2camera,
        method=cv2.CALIB_HAND_EYE_TSAI
    )

    # Build 4x4 homogeneous transform
    T_camera2link4 = np.eye(4)
    T_camera2link4[:3, :3] = R_cam2link4
    T_camera2link4[:3, 3] = t_cam2link4.flatten()

    # Save result
    np.set_printoptions(precision=4, suppress=True)
    print("=== Calibration Result (T_camera2link4) ===")
    print(T_camera2link4)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(T_camera2link4.tolist(), f, indent=2)

    print(f"Saved calibration matrix to {OUTPUT_FILE}")


if __name__ == "__main__":
    run_handeye_calibration()
