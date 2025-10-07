from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2

import mediapipe as mp

# Allow importing from the project without installing as a package
PROJECT_ROOT = Path(__file__).resolve().parents[0]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gesture_recognizer import GestureFeatureExtractor  # noqa: E402


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
        help="Camera index to use (default: 0).",
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
    capture = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not capture or not capture.isOpened():
        raise RuntimeError(f"Unable to open camera index {args.camera}")

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
