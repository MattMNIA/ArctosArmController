from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

import mediapipe as mp

# Allow importing from the project without installing as a package
PROJECT_ROOT = Path(__file__).resolve().parents[0]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gesture_recognizer import GestureFeatureExtractor  # noqa: E402


class IPCameraCapture:
    """Wrapper for IP camera that mimics cv2.VideoCapture interface with background frame grabbing."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._capture = cv2.VideoCapture(url)
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(f"Failed to open IP camera at {url}")

        # Set buffer size to minimum to reduce latency
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Background frame grabbing for reduced latency
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_available = False
        self._stop_event = threading.Event()
        self._grab_thread = threading.Thread(
            target=self._grab_frames_loop,
            daemon=True,
            name="ip-camera-grab"
        )
        self._grab_thread.start()

    def _grab_frames_loop(self) -> None:
        """Continuously grab frames in background to keep buffer fresh."""
        while not self._stop_event.is_set():
            if not self._capture or not self._capture.isOpened():
                break
            try:
                ret, frame = self._capture.read()
                if ret and frame is not None:
                    with self._frame_lock:
                        self._latest_frame = frame
                        self._frame_available = True
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.01)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read the latest frame from the camera (non-blocking)."""
        with self._frame_lock:
            if self._frame_available and self._latest_frame is not None:
                return True, self._latest_frame.copy()
            return False, None

    def isOpened(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def release(self) -> None:
        self._stop_event.set()
        if self._grab_thread and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=0.5)
        if self._capture and self._capture.isOpened():
            self._capture.release()


def create_capture(camera_index: int, ip_camera_url: Optional[str]) -> Union[cv2.VideoCapture, IPCameraCapture]:
    """Create a camera capture object from either a local camera index or IP camera URL."""
    if ip_camera_url:
        print(f"Using IP camera: {ip_camera_url}")
        return IPCameraCapture(ip_camera_url)
    else:
        print(f"Using local camera index: {camera_index}")
        capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not capture or not capture.isOpened():
            # Try without CAP_DSHOW (for macOS/Linux)
            capture = cv2.VideoCapture(camera_index)
        return capture


GESTURE_HINTS = {
    "neutral": "Relax your hand and keep fingers apart",
    "rock_and_roll": "Extend index+pink and tuck middle/ring",
    "thumbs_down": "Point thumb downward with fist",
    "thumbs_up": "Raise thumb upward with fist",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect hand gesture samples using MediaPipe and save them as features for training."
    )
    parser.add_argument(
        "--gestures",
        nargs="+",
        default=["neutral", "rock_and_roll", "thumbs_down", "thumbs_up"],
        help=(
            "Names of gestures to capture. Each gesture will be captured sequentially. "
            "Include 'neutral' to record relaxed-hand negatives."
        ),
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=150,
        help="Number of samples to collect per gesture (per hand).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "gesture_dataset.csv",
        help="Path to the CSV file where samples will be saved.",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index to use for local camera (default: 0).",
    )
    parser.add_argument(
        "--ip-camera",
        type=str,
        default=None,
        help="IP camera URL to use instead of local camera (e.g., 'http://192.168.1.100:81/stream').",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.75,
        help="Minimum detection confidence required to record a sample.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        default=True,
        help="Append to the existing dataset instead of overwriting it. (default: True)",
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=2,
        help="Maximum number of hands to track simultaneously.",
    )
    return parser.parse_args()


def write_samples(
    output_path: Path,
    samples: List[Dict[str, float]],
    feature_count: int,
    append: bool,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["gesture", "handedness"] + [f"f{i}" for i in range(feature_count)]
    write_header = not append or not output_path.exists()
    mode = "a" if append and output_path.exists() else "w"
    with output_path.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in samples:
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    capture = create_capture(args.camera, args.ip_camera)
    if not capture or not capture.isOpened():
        camera_desc = args.ip_camera if args.ip_camera else f"index {args.camera}"
        raise RuntimeError(f"Unable to open camera {camera_desc}")

    feature_extractor = GestureFeatureExtractor()
    hands = mp.solutions.hands.Hands(
        max_num_hands=args.max_hands,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    )

    samples: List[Dict[str, float]] = []
    feature_count: Optional[int] = None
    window_name = "Gesture Dataset Collector"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        for gesture in args.gestures:
            collected = 0
            recording = False
            while collected < args.samples:
                success, frame = capture.read()
                if not success:
                    print("Warning: failed to read frame from camera")
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb)

                hint = GESTURE_HINTS.get(gesture, "Hold pose steady for clean samples")
                overlay_lines = [
                    f"Gesture: {gesture} ({collected}/{args.samples})",
                    f"Recording: {'ON' if recording else 'OFF'} [space to toggle]",
                    f"Hint: {hint}",
                    "Press 'n' to skip gesture, 'q' to quit",
                ]

                if recording and results.multi_hand_landmarks and results.multi_handedness:
                    for landmark_list, handedness in zip(
                        results.multi_hand_landmarks, results.multi_handedness
                    ):
                        score = handedness.classification[0].score
                        if score < args.min_confidence:
                            continue
                        hand_label = handedness.classification[0].label
                        features = feature_extractor.extract(
                            list(landmark_list.landmark), hand_label
                        )
                        if features is None:
                            continue
                        if feature_count is None:
                            feature_count = len(features)
                        sample = {
                            "gesture": gesture,
                            "handedness": hand_label,
                        }
                        sample.update({f"f{i}": float(value) for i, value in enumerate(features)})
                        samples.append(sample)
                        collected += 1
                        if collected >= args.samples:
                            recording = False
                            break

                for idx, text in enumerate(overlay_lines):
                    cv2.putText(
                        frame,
                        text,
                        (10, 20 + idx * 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0) if recording else (200, 200, 200),
                        1,
                        cv2.LINE_AA,
                    )

                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    raise KeyboardInterrupt
                if key == ord("n"):
                    print(f"Skipping gesture '{gesture}' after collecting {collected} samples")
                    break
                if key == ord(" "):
                    recording = not recording
                if key == ord("c"):
                    recording = False
                    samples = [s for s in samples if s["gesture"] != gesture]
                    collected = 0

            print(f"Captured {collected} samples for '{gesture}'")

    except KeyboardInterrupt:
        print("\nCapture interrupted by user")
    finally:
        hands.close()
        capture.release()
        cv2.destroyWindow(window_name)

    if not samples:
        print("No samples collected; nothing to save.")
        return

    if feature_count is None:
        raise RuntimeError("No valid samples captured; feature extraction failed.")

    write_samples(args.output, samples, feature_count, args.append)
    print(f"Saved {len(samples)} samples to {args.output}")


if __name__ == "__main__":
    main()
