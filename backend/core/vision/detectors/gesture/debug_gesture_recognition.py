from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Sequence, Tuple

import cv2
import warnings
warnings.filterwarnings(
    "ignore",
    message="SymbolDatabase.GetPrototype() is deprecated",
    category=UserWarning
)
import mediapipe as mp

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gesture_recognizer import GestureRecognizer  # noqa: E402


drawing_utils = mp.solutions.drawing_utils
drawing_styles = mp.solutions.drawing_styles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live preview of gesture recognition results using the current model and config."
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index to use (default: 0)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "backend" / "config" / "gestures.yml",
        help="Path to gestures.yml config (default uses repo config)",
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=2,
        help="Maximum number of hands to process",
    )
    parser.add_argument(
        "--min-detect",
        type=float,
        default=0.7,
        help="MediaPipe minimum detection confidence",
    )
    parser.add_argument(
        "--min-track",
        type=float,
        default=0.6,
        help="MediaPipe minimum tracking confidence",
    )
    parser.add_argument(
        "--save-log",
        type=Path,
        default=None,
        help="Optional path to append timestamped gesture events for post-analysis",
    )
    return parser.parse_args()


def append_log(log_path: Optional[Path], message: str) -> None:
    if log_path is None:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


def _landmarks_to_bbox(landmarks: Sequence[object], frame_shape: Tuple[int, int, int]) -> tuple[int, int, int, int]:
    h, w = frame_shape[:2]
    xs = [int(getattr(lm, "x", 0.0) * w) for lm in landmarks]
    ys = [int(getattr(lm, "y", 0.0) * h) for lm in landmarks]
    if not xs or not ys:
        return 0, 0, w, h
    min_x = max(min(xs) - 10, 0)
    min_y = max(min(ys) - 10, 0)
    max_x = min(max(xs) + 10, w)
    max_y = min(max(ys) + 10, h)
    return min_x, min_y, max_x, max_y


def _format_top_predictions(recognizer: GestureRecognizer, landmarks, handed_label: str) -> list[str]:
    classifier = getattr(recognizer, "_classifier", None)
    feature_extractor = getattr(recognizer, "_feature_extractor", None)
    label_encoder = getattr(recognizer, "_label_encoder", None)
    if classifier is None or feature_extractor is None or label_encoder is None:
        return ["Classifier unavailable"]

    features = feature_extractor.extract(list(landmarks), handed_label)
    if features is None:
        return ["Feature extraction failed"]

    try:
        proba = classifier.predict_proba([features])[0]
    except Exception as exc:  # pragma: no cover - defensive
        return [f"predict_proba error: {exc}"]

    indexed = sorted(((float(score), idx) for idx, score in enumerate(proba)), reverse=True)
    top = indexed[:3]
    lines: list[str] = []
    for score, idx in top:
        encoded = classifier.classes_[idx]
        try:
            label = label_encoder.inverse_transform([encoded])[0]
        except Exception:
            label = str(encoded)
        lines.append(f"{label}: {score:0.2f}")
    return lines if lines else ["No classes"]


def main() -> None:
    args = parse_args()

    recognizer = GestureRecognizer(args.config)
    if not recognizer.enabled:
        print("WARNING: Gesture classifier not loaded. Check the model path in gestures.yml.")

    capture = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not capture or not capture.isOpened():
        raise RuntimeError(f"Unable to open camera index {args.camera}")

    hands = mp.solutions.hands.Hands(
        max_num_hands=args.max_hands,
        min_detection_confidence=args.min_detect,
        min_tracking_confidence=args.min_track,
    )

    window_name = "Gesture Debug Preview"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        while True:
            success, frame = capture.read()
            if not success:
                print("Warning: failed to read frame from camera")
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            events, overlays = recognizer.process(
                results.multi_hand_landmarks,
                results.multi_handedness,
            )

            hand_count = len(results.multi_hand_landmarks) if results.multi_hand_landmarks else 0

            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    drawing_utils.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                        drawing_styles.get_default_hand_landmarks_style(),
                        drawing_styles.get_default_hand_connections_style(),
                    )

                    classification = handedness.classification[0]
                    land_list = hand_landmarks.landmark

                    x1, y1, x2, y2 = _landmarks_to_bbox(land_list, tuple(frame.shape))
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 180, 255), 1)

                    info_lines = [
                        f"Hand: {classification.label} score={classification.score:0.2f}",
                    ]
                    info_lines.extend(
                        _format_top_predictions(recognizer, land_list, classification.label)
                    )

                    for idx, line in enumerate(info_lines):
                        cv2.putText(
                            frame,
                            line,
                            (x1 + 5, max(y1 - 10 - idx * 18, 15)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 255),
                            1,
                            cv2.LINE_AA,
                        )

            header_lines = [
                "[Gesture Debug] press Q or ESC to exit",
                f"Hands detected: {hand_count}",
                f"Model loaded: {'yes' if recognizer.enabled else 'NO'}",
            ]

            prob_threshold = getattr(recognizer, "_probability_threshold", None)
            if prob_threshold is not None:
                header_lines.append(f"Confidence threshold: {prob_threshold:0.2f}")

            if overlays:
                header_lines.extend(overlays)
            else:
                header_lines.append("Overlay: (no stable predictions yet)")

            for idx, text in enumerate(header_lines):
                cv2.putText(
                    frame,
                    text,
                    (10, 25 + idx * 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6 if idx == 0 else 0.55,
                    (0, 255, 0) if idx == 0 else (200, 255, 200),
                    1,
                    cv2.LINE_AA,
                )

            for event_idx, event in enumerate(events):
                status = (
                    f"{event.change.upper()}: {event.event} ({event.label}) conf={event.confidence:0.2f}"
                )
                append_log(args.save_log, status)
                cv2.putText(
                    frame,
                    status,
                    (10, frame.shape[0] - 10 - event_idx * 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 200, 255) if event.change == "start" else (200, 200, 200),
                    1,
                    cv2.LINE_AA,
                )

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    finally:
        hands.close()
        capture.release()
        cv2.destroyWindow(window_name)


if __name__ == "__main__":
    main()
