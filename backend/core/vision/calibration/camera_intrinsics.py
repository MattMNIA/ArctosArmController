import argparse
import importlib
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import cv2
from cv2 import aruco
import numpy as np
import yaml

from core.motion_service import MotionService
from core.teleop_controller import TeleopController, DriverProtocol
from core.vision.cameras import CameraBase, IPCamera


TELEOP_INPUT_CONTROLLERS: Dict[str, str] = {
    "keyboard": "core.input.keyboard_input:KeyboardController",
    "xbox": "core.input.xbox_input:XboxController",
    "finger": "core.input.finger_input:FingerInput",
    "finger_slider": "core.input.finger_slider_input:FingerSliderInput",
}


# ------------------------------
# Default ChArUco board parameters. Override via CLI if needed.
DEFAULT_ARUCO_DICT = cv2.aruco.DICT_6X6_250
DEFAULT_SQUARES_VERTICALLY = 7
DEFAULT_SQUARES_HORIZONTALLY = 5
DEFAULT_SQUARE_LENGTH = 0.03  # meters
DEFAULT_MARKER_LENGTH = 0.015  # meters
DEFAULT_SAVE_PATH = "calibration_images"
# ------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactively capture ChArUco images from an IP or USB camera, "
            "calibrate intrinsics, and estimate the camera pose relative to the "
            "board for PyBullet placement."
        )
    )
    parser.add_argument(
        "--ip-url",
        default="http://192.168.50.254:81/stream",
        help="Optional override for the IP camera URL; defaults to the IPCamera class setting.",
    )
    parser.add_argument(
        "--joint-poses-file",
        type=Path,
        help="Path to a YAML/JSON file describing joint angle waypoints for automated capture.",
    )
    parser.add_argument(
        "--save-path",
        default=DEFAULT_SAVE_PATH,
        help="Directory to store captured calibration frames.",
    )
    parser.add_argument(
        "--min-corners",
        type=int,
        default=20,
        help="Minimum interpolated ChArUco corners required to accept a frame.",
    )
    parser.add_argument(
        "--aruco-dict",
        type=int,
        default=DEFAULT_ARUCO_DICT,
        help="OpenCV ArUco dictionary id (e.g. cv2.aruco.DICT_6X6_250).",
    )
    parser.add_argument(
        "--squares-vert",
        type=int,
        default=DEFAULT_SQUARES_VERTICALLY,
        help="Number of chessboard squares vertically.",
    )
    parser.add_argument(
        "--squares-horz",
        type=int,
        default=DEFAULT_SQUARES_HORIZONTALLY,
        help="Number of chessboard squares horizontally.",
    )
    parser.add_argument(
        "--square-length",
        type=float,
        default=DEFAULT_SQUARE_LENGTH,
        help="Length of a chessboard square in meters.",
    )
    parser.add_argument(
        "--marker-length",
        type=float,
        default=DEFAULT_MARKER_LENGTH,
        help="Length of an ArUco marker side in meters.",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip live capture and only process images already in --save-path.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable preview windows (useful on headless systems).",
    )
    parser.add_argument(
        "--pose-settle-time",
        type=float,
        default=0.75,
        help="Seconds the joints must remain within tolerance before capturing.",
    )
    parser.add_argument(
        "--pose-timeout",
        type=float,
        default=20.0,
        help="Maximum seconds to wait for each joint target to be reached before aborting.",
    )
    parser.add_argument(
        "--joint-position-tolerance",
        type=float,
        default=0.02,
        help="Joint error tolerance (radians) for considering a pose settled.",
    )
    parser.add_argument(
        "--joint-velocity-tolerance",
        type=float,
        default=0.05,
        help="Joint velocity tolerance (rad/s) during settling.",
    )
    parser.add_argument(
        "--max-capture-attempts",
        type=int,
        default=10,
        help="Maximum captured frames to try per pose before failing.",
    )
    parser.add_argument(
        "--auto-capture-delay",
        type=float,
        default=0.2,
        help="Optional pause (seconds) after a pose settles before grabbing an image.",
    )
    parser.add_argument(
        "--teleop-input",
        choices=sorted(TELEOP_INPUT_CONTROLLERS),
        help=(
            "Enable teleoperation control using the specified input device to move the arm "
            "between captures (e.g. keyboard, xbox, finger)."
        ),
    )
    parser.add_argument(
        "--teleop-rate",
        type=float,
        default=100.0,
        help="Polling frequency (Hz) for the teleop loop when --teleop-input is used.",
    )
    return parser.parse_args()


def open_video_capture(url: str) -> CameraBase:
    camera = IPCamera(url)
    if not camera.is_opened():
        raise RuntimeError("Unable to open the configured IP camera stream.")
    return camera


def create_input_controller(name: str) -> Any:
    key = name.lower()
    spec = TELEOP_INPUT_CONTROLLERS.get(key)
    if spec is None:
        available = ", ".join(sorted(TELEOP_INPUT_CONTROLLERS))
        raise ValueError(f"Unknown teleop input '{name}'. Available options: {available}.")

    module_name, class_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(
            f"Failed to import teleop input module '{module_name}' for '{name}': {exc}"
        ) from exc

    try:
        controller_cls = getattr(module, class_name)
    except AttributeError as exc:
        raise RuntimeError(
            f"Teleop input class '{class_name}' not found in module '{module_name}'."
        ) from exc

    return controller_cls()


def teleop_loop(controller: TeleopController, stop_event: threading.Event, rate_hz: float) -> None:
    sleep_dt = 0.0
    if rate_hz > 0:
        sleep_dt = 1.0 / rate_hz

    try:
        while not stop_event.is_set():
            controller.teleop_step()
            if sleep_dt > 0:
                time.sleep(sleep_dt)
    finally:
        controller.stop_all()


def load_joint_pose_sequence(file_path: Path) -> List[Dict[str, Any]]:
    if not file_path.exists():
        raise FileNotFoundError(f"Joint pose file {file_path} does not exist.")

    with file_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if data is None:
        raise ValueError(f"Joint pose file {file_path} is empty.")

    if isinstance(data, dict):
        poses_raw = data.get("poses")
        if poses_raw is None:
            raise ValueError(
                "Joint pose file must contain a top-level 'poses' list or be a list itself."
            )
    elif isinstance(data, list):
        poses_raw = data
    else:
        raise ValueError("Joint pose file must be a list or an object containing a 'poses' list.")

    poses: List[Dict[str, Any]] = []
    for idx, pose in enumerate(poses_raw):
        label: Optional[str] = None
        settle_s: Optional[float] = None
        joints: Optional[Sequence[float]] = None

        if isinstance(pose, dict):
            joints = pose.get("joints") or pose.get("q")
            label = pose.get("label")
            hold_val = pose.get("settle_s", pose.get("hold_s"))
            if hold_val is not None:
                settle_s = float(hold_val)
        elif isinstance(pose, (list, tuple)):
            joints = pose
        else:
            raise ValueError(f"Pose entry #{idx} is not a recognised format: {pose!r}")

        if joints is None:
            raise ValueError(f"Pose entry #{idx} is missing 'joints' / 'q' values.")

        joints_list = [float(value) for value in joints]
        poses.append(
            {
                "index": idx,
                "label": label,
                "target": joints_list,
                "settle_s": settle_s,
            }
        )

    if not poses:
        raise ValueError(f"Joint pose file {file_path} did not contain any waypoints.")

    return poses


def move_arm_and_wait(
    service: MotionService,
    target: Sequence[float],
    settle_time: float,
    timeout: float,
    position_tolerance: float,
    velocity_tolerance: float,
) -> List[float]:
    service.send_joint_targets(list(target))

    start_time = time.time()
    settled_since: Optional[float] = None
    last_q: List[float] = []

    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(
                f"Timed out waiting for joint target {target} after {timeout:.1f}s."
            )

        feedback = service.driver.get_feedback() or {}
        q = feedback.get("q")
        dq = feedback.get("dq") or []

        if q:
            last_q = [float(val) for val in q]

        if not q or len(q) < len(target):
            time.sleep(0.05)
            continue

        position_errors = [abs(target[i] - q[i]) for i in range(len(target))]
        max_error = max(position_errors)

        velocity_samples = dq[: len(target)] if dq else []
        max_velocity = max(abs(v) for v in velocity_samples) if velocity_samples else 0.0

        if max_error <= position_tolerance and max_velocity <= velocity_tolerance:
            if settled_since is None:
                settled_since = time.time()
            elif time.time() - settled_since >= settle_time:
                return last_q
        else:
            settled_since = None

        time.sleep(0.05)


def capture_sequence_with_motion(
    motion_service: MotionService,
    camera: CameraBase,
    board: aruco.CharucoBoard,
    dictionary: cv2.aruco.Dictionary,
    save_dir: Path,
    min_corners: int,
    poses: Sequence[Dict[str, Any]],
    settle_time: float,
    pose_timeout: float,
    position_tolerance: float,
    velocity_tolerance: float,
    max_capture_attempts: int,
    auto_capture_delay: float,
    show_preview: bool,
) -> List[Dict[str, Any]]:
    print("[INFO] Starting automated capture sequence driven by MotionService.")
    save_dir.mkdir(parents=True, exist_ok=True)

    frame_index = len(list(save_dir.glob("charuco_*.png")))
    capture_metadata: List[Dict[str, Any]] = []

    for pose in poses:
        target = pose["target"]
        label = pose.get("label")
        pose_settle_time = pose.get("settle_s") or settle_time

        print(
            f"[INFO] Moving to pose #{pose['index']} "
            f"(label={label!r}) with target joints {target}."
        )

        achieved_q = move_arm_and_wait(
            motion_service,
            target,
            pose_settle_time,
            pose_timeout,
            position_tolerance,
            velocity_tolerance,
        )

        if auto_capture_delay > 0:
            time.sleep(auto_capture_delay)

        success = False
        attempts = 0
        last_frame: Optional[np.ndarray] = None

        while attempts < max_capture_attempts:
            ret, frame = camera.read()
            if not ret:
                print("[WARN] Unable to read frame from camera; retrying...")
                attempts += 1
                time.sleep(0.1)
                continue

            last_frame = frame
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = aruco.detectMarkers(gray, dictionary)

            charuco_corners: Optional[np.ndarray] = None
            charuco_ids: Optional[np.ndarray] = None
            if ids is not None and len(ids) > 0:
                _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                    corners, ids, gray, board
                )

            annotated = frame.copy()
            if ids is not None:
                annotated = aruco.drawDetectedMarkers(annotated, corners, ids)

            if charuco_corners is not None and charuco_ids is not None:
                annotated = cv2.aruco.drawDetectedCornersCharuco(
                    annotated, charuco_corners, charuco_ids, (0, 255, 0)
                )

            if show_preview:
                cv2.imshow("Calibration Capture", annotated)
                cv2.waitKey(1)

            if (
                charuco_corners is not None
                and charuco_ids is not None
                and len(charuco_corners) >= min_corners
            ):
                filename = save_dir / f"charuco_{frame_index:03d}.png"
                cv2.imwrite(str(filename), frame)
                print(f"[INFO] Saved {filename} for pose #{pose['index']}")
                capture_metadata.append(
                    {
                        "image": filename.name,
                        "pose_index": pose["index"],
                        "label": label,
                        "target_joint_angles": list(target),
                        "achieved_joint_angles": achieved_q,
                        "timestamp": time.time(),
                    }
                )
                frame_index += 1
                success = True
                break

            attempts += 1
            time.sleep(0.1)

        if not success:
            raise RuntimeError(
                f"Failed to detect ChArUco board for pose #{pose['index']} after "
                f"{max_capture_attempts} attempts."
            )

    return capture_metadata


def create_charuco_board(
    squares_vert: int,
    squares_horz: int,
    square_length: float,
    marker_length: float,
    dictionary_id: int,
) -> Tuple[aruco.CharucoBoard, cv2.aruco.Dictionary]:
    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    board = cv2.aruco.CharucoBoard(
        (squares_horz, squares_vert), square_length, marker_length, dictionary
    )
    return board, dictionary


def capture_charuco_images(
    camera: CameraBase,
    board: aruco.CharucoBoard,
    dictionary: cv2.aruco.Dictionary,
    save_dir: Path,
    min_corners: int,
    show_preview: bool = True,
    feedback_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    metadata_defaults: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    print("[INFO] Press SPACE to capture frame, ESC to finish.")
    save_dir.mkdir(parents=True, exist_ok=True)

    frame_index = len(list(save_dir.glob("charuco_*.png")))
    capture_metadata: List[Dict[str, Any]] = []
    while True:
        ret, frame = camera.read()
        if not ret:
            print("[WARN] Frame grab failed. Check the camera stream.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = aruco.detectMarkers(gray, dictionary)

        charuco_corners: Optional[np.ndarray] = None
        charuco_ids: Optional[np.ndarray] = None
        if ids is not None and len(ids) > 0:
            _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                corners, ids, gray, board
            )

        annotated = frame.copy()
        if ids is not None:
            annotated = aruco.drawDetectedMarkers(annotated, corners, ids)

        if charuco_corners is not None and charuco_ids is not None:
            annotated = cv2.aruco.drawDetectedCornersCharuco(
                annotated, charuco_corners, charuco_ids, (0, 255, 0)
            )

        if show_preview:
            cv2.imshow("Calibration Capture", annotated)

        key = cv2.waitKey(1) & 0xFF if show_preview else 255
        if key == 27:  # ESC
            break
        if key == 32 and charuco_corners is not None and charuco_ids is not None:
            if len(charuco_corners) < min_corners:
                print(
                    f"[WARN] Only {len(charuco_corners)} corners detected (< {min_corners}). "
                    "Reposition the board and try again."
                )
                continue
            file_path = save_dir / f"charuco_{frame_index:03d}.png"
            cv2.imwrite(str(file_path), frame)
            print(f"[INFO] Saved {file_path}")
            metadata_entry: Dict[str, Any] = {
                "image": file_path.name,
                "timestamp": time.time(),
            }

            if metadata_defaults:
                metadata_entry.update(metadata_defaults)

            if feedback_provider is not None:
                try:
                    feedback = feedback_provider() or {}
                except Exception as exc:
                    print(f"[WARN] Unable to read joint feedback: {exc}")
                    feedback = {}
                joints = feedback.get("q") if isinstance(feedback, dict) else None
                velocities = feedback.get("dq") if isinstance(feedback, dict) else None
                if joints:
                    metadata_entry["achieved_joint_angles"] = [float(val) for val in joints]
                if velocities:
                    metadata_entry["joint_velocities"] = [float(val) for val in velocities]

            capture_metadata.append({k: v for k, v in metadata_entry.items() if v is not None})
            frame_index += 1

    return capture_metadata


def load_charuco_detections(
    image_paths: Iterable[Path],
    board: aruco.CharucoBoard,
    dictionary: cv2.aruco.Dictionary,
    min_corners: int,
) -> Tuple[
    List[np.ndarray],
    List[np.ndarray],
    Optional[Tuple[int, int]],
    List[Tuple[Path, np.ndarray, np.ndarray]],
]:
    all_corners: List[np.ndarray] = []
    all_ids: List[np.ndarray] = []
    detections: List[Tuple[Path, np.ndarray, np.ndarray]] = []
    image_size: Optional[Tuple[int, int]] = None

    for image_path in image_paths:
        frame = cv2.imread(str(image_path))
        if frame is None:
            print(f"[WARN] Unable to load {image_path}, skipping.")
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = aruco.detectMarkers(gray, dictionary)
        if ids is None or len(ids) == 0:
            print(f"[WARN] No ArUco markers detected in {image_path}, skipping.")
            continue

        _, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
            corners, ids, gray, board
        )
        if charuco_corners is None or charuco_ids is None:
            print(f"[WARN] ChArUco interpolation failed for {image_path}, skipping.")
            continue

        if len(charuco_corners) < min_corners:
            print(
                f"[WARN] Insufficient corners ({len(charuco_corners)}) in {image_path}, skipping."
            )
            continue

        charuco_corners_np = np.asarray(charuco_corners)
        charuco_ids_np = np.asarray(charuco_ids)

        all_corners.append(charuco_corners_np)
        all_ids.append(charuco_ids_np)
        detections.append((image_path, charuco_corners_np, charuco_ids_np))

        height, width = frame.shape[:2]
        image_size = (int(width), int(height))

    return all_corners, all_ids, image_size, detections


def calibrate_camera(
    board: aruco.CharucoBoard,
    all_corners: Sequence[np.ndarray],
    all_ids: Sequence[np.ndarray],
    image_size: Optional[Tuple[int, int]],
) -> Tuple[float, np.ndarray, np.ndarray, List[np.ndarray], List[np.ndarray]]:
    if image_size is None or len(all_corners) == 0:
        raise RuntimeError("Not enough valid ChArUco detections to calibrate the camera.")

    reprojection_error, camera_matrix, dist_coeffs, rvecs, tvecs = (
        aruco.calibrateCameraCharuco(
            charucoCorners=list(all_corners),
            charucoIds=list(all_ids),
            board=board,
            imageSize=image_size,
            cameraMatrix=None,  # type: ignore[arg-type]
            distCoeffs=None,  # type: ignore[arg-type]
        )
    )
    return reprojection_error, camera_matrix, dist_coeffs, list(rvecs), list(tvecs)


def rotation_matrix_to_quaternion(r: np.ndarray) -> np.ndarray:
    # Quaternion in (x, y, z, w)
    q = np.empty(4, dtype=float)
    trace = float(np.trace(r))
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q[3] = 0.25 * s
        q[0] = (r[2, 1] - r[1, 2]) / s
        q[1] = (r[0, 2] - r[2, 0]) / s
        q[2] = (r[1, 0] - r[0, 1]) / s
    else:
        diag = [r[0, 0], r[1, 1], r[2, 2]]
        idx = int(np.argmax(diag))
        if idx == 0:
            s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            q[3] = (r[2, 1] - r[1, 2]) / s
            q[0] = 0.25 * s
            q[1] = (r[0, 1] + r[1, 0]) / s
            q[2] = (r[0, 2] + r[2, 0]) / s
        elif idx == 1:
            s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            q[3] = (r[0, 2] - r[2, 0]) / s
            q[0] = (r[0, 1] + r[1, 0]) / s
            q[1] = 0.25 * s
            q[2] = (r[1, 2] + r[2, 1]) / s
        else:
            s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            q[3] = (r[1, 0] - r[0, 1]) / s
            q[0] = (r[0, 2] + r[2, 0]) / s
            q[1] = (r[1, 2] + r[2, 1]) / s
            q[2] = 0.25 * s
    return q


def rotation_matrix_to_euler(r: np.ndarray) -> Tuple[float, float, float]:
    # Returns roll-pitch-yaw in radians using XYZ convention.
    sy = math.sqrt(r[0, 0] * r[0, 0] + r[1, 0] * r[1, 0])
    singular = sy < 1e-6
    if not singular:
        roll = math.atan2(r[2, 1], r[2, 2])
        pitch = math.atan2(-r[2, 0], sy)
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:
        roll = math.atan2(-r[1, 2], r[1, 1])
        pitch = math.atan2(-r[2, 0], sy)
        yaw = 0.0
    return roll, pitch, yaw


def average_pose(rvecs: Sequence[np.ndarray], tvecs: Sequence[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    if len(rvecs) == 0:
        raise RuntimeError("No pose estimates available to average.")

    quaternions: List[np.ndarray] = []
    translations: List[np.ndarray] = []
    for rvec, tvec in zip(rvecs, tvecs):
        rotation_matrix, _ = cv2.Rodrigues(rvec)
        quat = rotation_matrix_to_quaternion(rotation_matrix)
        if quat[3] < 0:  # Ensure consistent hemisphere
            quat *= -1
        quaternions.append(quat)
        translations.append(tvec.reshape(3))

    mean_quat = np.mean(quaternions, axis=0)
    mean_quat /= np.linalg.norm(mean_quat)

    x, y, z, w = mean_quat
    mean_rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )

    mean_translation = np.mean(translations, axis=0)
    return mean_rotation, mean_translation


def estimate_poses(
    detections: Sequence[Tuple[Path, np.ndarray, np.ndarray]],
    board: aruco.CharucoBoard,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> List[Tuple[Path, np.ndarray, np.ndarray]]:
    poses: List[Tuple[Path, np.ndarray, np.ndarray]] = []
    for image_path, corners, ids in detections:
        valid, rvec, tvec = aruco.estimatePoseCharucoBoard(  # type: ignore[arg-type]
            charucoCorners=corners,
            charucoIds=ids,
            board=board,
            cameraMatrix=camera_matrix,
            distCoeffs=dist_coeffs,
        )
        if not valid:
            print(f"[WARN] Pose estimation failed for {image_path}.")
            continue
        poses.append((image_path, rvec, tvec))
    return poses


def poses_to_yaml(
    poses: Sequence[Tuple[Path, np.ndarray, np.ndarray]],
    metadata_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[dict]:
    metadata_lookup = metadata_lookup or {}
    pose_entries: List[dict] = []
    for image_path, rvec, tvec in poses:
        rotation_matrix, _ = cv2.Rodrigues(rvec)
        quaternion = rotation_matrix_to_quaternion(rotation_matrix)
        euler = rotation_matrix_to_euler(rotation_matrix)
        pose_entries.append(
            {
                "image": image_path.name,
                "rvec": rvec.reshape(-1).tolist(),
                "tvec": tvec.reshape(-1).tolist(),
                "rotation_matrix": rotation_matrix.tolist(),
                "quaternion_xyzw": quaternion.tolist(),
                "euler_rpy_rad": list(euler),
            }
        )

        extra = metadata_lookup.get(image_path.name)
        if extra:
            if extra.get("label") is not None:
                pose_entries[-1]["pose_label"] = extra["label"]
            if "pose_index" in extra:
                pose_entries[-1]["pose_index"] = extra["pose_index"]
            if "target_joint_angles" in extra:
                pose_entries[-1]["target_joint_angles"] = list(extra["target_joint_angles"])
            if "achieved_joint_angles" in extra:
                pose_entries[-1]["achieved_joint_angles"] = list(extra["achieved_joint_angles"])
            if "timestamp" in extra:
                pose_entries[-1]["capture_timestamp"] = float(extra["timestamp"])
    return pose_entries


def save_calibration_results(
    output_path: Path,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    reprojection_error: float,
    poses: Sequence[Tuple[Path, np.ndarray, np.ndarray]],
    average_rotation: Optional[np.ndarray],
    average_translation: Optional[np.ndarray],
    capture_metadata: Optional[Sequence[Dict[str, Any]]] = None,
) -> None:
    metadata_lookup: Dict[str, Dict[str, Any]] = {}
    if capture_metadata:
        metadata_lookup = {
            str(entry.get("image")): dict(entry) for entry in capture_metadata if "image" in entry
        }

    output = {
        "camera_matrix": camera_matrix.tolist(),
        "dist_coeffs": dist_coeffs.tolist(),
        "reprojection_error": float(reprojection_error),
        "charuco_board_frame": {
            "origin": "Board center with Z normal pointing out of the board",
            "x_axis": "Points right when looking at the board",
            "y_axis": "Points up",
            "z_axis": "Points towards the camera when the board faces the camera",
        },
        "poses": poses_to_yaml(poses, metadata_lookup=metadata_lookup),
    }

    if capture_metadata:
        output["captures"] = list(capture_metadata)

    if average_rotation is not None and average_translation is not None:
        quaternion = rotation_matrix_to_quaternion(average_rotation)
        euler = rotation_matrix_to_euler(average_rotation)
        transform = np.eye(4)
        transform[:3, :3] = average_rotation
        transform[:3, 3] = average_translation
        output["average_pose"] = {
            "rotation_matrix": average_rotation.tolist(),
            "translation_m": average_translation.tolist(),
            "quaternion_xyzw": quaternion.tolist(),
            "euler_rpy_rad": list(euler),
            "transform_4x4": transform.tolist(),
            "description": (
                "Transforms board points into camera coordinates. "
                "Use the inverse to place the camera in PyBullet given the board frame."
            ),
        }

    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(output, f, sort_keys=False)

    print(f"[INFO] Calibration saved to {output_path}")


def main() -> None:
    args = parse_args()
    save_dir = Path(args.save_path)

    if args.skip_capture and args.joint_poses_file:
        print("[WARN] --joint-poses-file was provided but capture is skipped; it will be ignored.")

    if args.teleop_input and args.joint_poses_file:
        print(
            "[WARN] Both --teleop-input and --joint-poses-file were provided. Teleop control "
            "will be used for motion and the joint pose sequence will be ignored."
        )

    board, dictionary = create_charuco_board(
        squares_vert=args.squares_vert,
        squares_horz=args.squares_horz,
        square_length=args.square_length,
        marker_length=args.marker_length,
        dictionary_id=args.aruco_dict,
    )

    camera: Optional[CameraBase] = None
    capture_metadata: List[Dict[str, Any]] = []
    try:
        if not args.skip_capture:
            camera = open_video_capture(args.ip_url)
            if args.teleop_input:
                motion_service = MotionService()
                teleop_stop_event = threading.Event()
                teleop_thread: Optional[threading.Thread] = None
                teleop_controller: Optional[TeleopController] = None
                input_controller: Any = None
                try:
                    print("[INFO] Starting MotionService for teleop-driven capture.")
                    motion_service.start()

                    print(f"[INFO] Initializing teleop input '{args.teleop_input}'.")
                    input_controller = create_input_controller(args.teleop_input)
                    driver = motion_service.driver
                    required_methods = ["start_joint_velocity", "stop_joint_velocity"]
                    missing = [name for name in required_methods if not hasattr(driver, name)]
                    if missing:
                        raise RuntimeError(
                            "The active driver does not support teleop velocity control. Missing methods: "
                            + ", ".join(missing)
                        )

                    teleop_controller = TeleopController(
                        input_controller=input_controller,
                        driver=cast(DriverProtocol, driver),
                        motion_service=motion_service,
                    )

                    teleop_stop_event.clear()
                    teleop_thread = threading.Thread(
                        target=teleop_loop,
                        args=(teleop_controller, teleop_stop_event, args.teleop_rate),
                        daemon=True,
                    )
                    teleop_thread.start()

                    print(
                        "[INFO] Teleop control active. Use the selected input to maneuver the arm, "
                        "then press SPACE in the preview window to capture or ESC to finish."
                    )

                    def feedback_provider() -> Dict[str, Any]:
                        return motion_service.driver.get_feedback() or {}

                    capture_metadata = capture_charuco_images(
                        camera,
                        board,
                        dictionary,
                        save_dir,
                        min_corners=args.min_corners,
                        show_preview=not args.no_preview,
                        feedback_provider=feedback_provider,
                        metadata_defaults={
                            "capture_mode": "teleop",
                            "teleop_input": args.teleop_input,
                        },
                    )
                finally:
                    teleop_stop_event.set()
                    if teleop_thread is not None:
                        teleop_thread.join(timeout=2.0)
                    if teleop_controller is not None:
                        teleop_controller.stop_all()
                    if input_controller is not None and hasattr(input_controller, "close"):
                        try:
                            input_controller.close()
                        except Exception as exc:  # pragma: no cover - best effort logging
                            print(f"[WARN] Error while closing teleop input: {exc}")
                    try:
                        motion_service.stop()
                    except Exception as exc:
                        print(f"[WARN] Error while stopping MotionService: {exc}")
            elif args.joint_poses_file:
                joint_poses = load_joint_pose_sequence(args.joint_poses_file)
                motion_service = MotionService()
                try:
                    print("[INFO] Starting MotionService for automated capture.")
                    motion_service.start()
                    capture_metadata = capture_sequence_with_motion(
                        motion_service,
                        camera,
                        board,
                        dictionary,
                        save_dir,
                        min_corners=args.min_corners,
                        poses=joint_poses,
                        settle_time=args.pose_settle_time,
                        pose_timeout=args.pose_timeout,
                        position_tolerance=args.joint_position_tolerance,
                        velocity_tolerance=args.joint_velocity_tolerance,
                        max_capture_attempts=args.max_capture_attempts,
                        auto_capture_delay=args.auto_capture_delay,
                        show_preview=not args.no_preview,
                    )
                finally:
                    print("[INFO] Stopping MotionService.")
                    try:
                        motion_service.stop()
                    except Exception as exc:
                        print(f"[WARN] Error while stopping MotionService: {exc}")
            else:
                capture_metadata = capture_charuco_images(
                    camera,
                    board,
                    dictionary,
                    save_dir,
                    min_corners=args.min_corners,
                    show_preview=not args.no_preview,
                    feedback_provider=None,
                    metadata_defaults=None,
                )
    finally:
        if camera is not None:
            camera.release()
        if not args.no_preview:
            cv2.destroyAllWindows()

    image_paths = sorted(save_dir.glob("charuco_*.png"))
    if not image_paths:
        raise RuntimeError(
            f"No calibration images found in {save_dir}. Capture frames or verify the path."
        )

    all_corners, all_ids, image_size, detections = load_charuco_detections(
        image_paths, board, dictionary, args.min_corners
    )

    reprojection_error, camera_matrix, dist_coeffs, rvecs, tvecs = calibrate_camera(
        board, all_corners, all_ids, image_size
    )

    poses = estimate_poses(detections, board, camera_matrix, dist_coeffs)

    avg_rotation = avg_translation = None
    if poses:
        avg_rotation, avg_translation = average_pose(
            [cast(np.ndarray, rvec) for _, rvec, _ in poses],
            [cast(np.ndarray, tvec) for _, _, tvec in poses],
        )
        print("\n[INFO] Suggested average camera pose (board -> camera):")
        print(f"Rotation matrix:\n{avg_rotation}")
        print(f"Translation (m): {avg_translation}")

    output_path = save_dir / "camera_intrinsics.yaml"
    save_calibration_results(
        output_path,
        camera_matrix,
        dist_coeffs,
        reprojection_error,
        poses,
        avg_rotation,
        avg_translation,
        capture_metadata,
    )

    print(
        "\n[INFO] Calibration complete. Use the inverse of the board->camera transform "
        "to position the camera in the PyBullet scene relative to the board."
    )


if __name__ == "__main__":
    main()