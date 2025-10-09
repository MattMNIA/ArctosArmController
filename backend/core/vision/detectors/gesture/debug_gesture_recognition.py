from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import mediapipe as mp

PROJECT_ROOT = Path(__file__).resolve().parents[0]
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
        default=PROJECT_ROOT / "gestures.yml",
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
    parser.add_argument(
        "--model",
        dest="models",
        type=Path,
        action="append",
        help="Optional path to a gesture model joblib file. Repeat to compare multiple models.",
    )
    parser.add_argument(
        "--prob-threshold",
        type=float,
        default=None,
        help="Override the gesture probability threshold for debugging.",
    )
    parser.add_argument(
        "--smoothing-window",
        type=int,
        default=None,
        help="Override the temporal smoothing window length.",
    )
    parser.add_argument(
        "--min-consensus",
        type=int,
        default=None,
        help="Override the minimum number of agreeing frames required for a stable prediction.",
    )
    parser.add_argument(
        "--max-history",
        type=int,
        default=None,
        help="Override the maximum history size maintained for smoothing.",
    )
    return parser.parse_args()


def append_log(log_path: Optional[Path], message: str) -> None:
    if log_path is None:
        return
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


@dataclass
class PerformanceStats:
    frame_count: int = 0
    total_duration: float = 0.0
    recent_durations: deque[float] = field(default_factory=lambda: deque(maxlen=180))
    max_duration: float = 0.0

    def record(self, duration: float) -> None:
        self.frame_count += 1
        self.total_duration += duration
        self.recent_durations.append(duration)
        if duration > self.max_duration:
            self.max_duration = duration

    @property
    def last_duration(self) -> Optional[float]:
        if not self.recent_durations:
            return None
        return self.recent_durations[-1]

    @property
    def recent_average(self) -> Optional[float]:
        if not self.recent_durations:
            return None
        return sum(self.recent_durations) / len(self.recent_durations)

    @property
    def overall_average(self) -> Optional[float]:
        if self.frame_count == 0:
            return None
        return self.total_duration / self.frame_count


@dataclass
class DebugModelOption:
    recognizer: GestureRecognizer
    name: str
    path: Optional[Path]
    metadata: Dict[str, Any]
    stats: PerformanceStats = field(default_factory=PerformanceStats)

    @property
    def resolved_path(self) -> Optional[Path]:
        return self.path or self.recognizer.model_path


def _build_model_options(args: argparse.Namespace) -> List[DebugModelOption]:
    config_path = args.config
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()

    requested_models: List[Optional[Path]] = list(args.models or [None])

    shared_overrides: Dict[str, Any] = {}
    if args.prob_threshold is not None:
        shared_overrides["probability_threshold"] = args.prob_threshold
    if args.smoothing_window is not None:
        shared_overrides["smoothing_window"] = args.smoothing_window
    if args.min_consensus is not None:
        shared_overrides["min_consensus"] = args.min_consensus
    if args.max_history is not None:
        shared_overrides["max_history"] = args.max_history

    options: List[DebugModelOption] = []
    for index, model_path in enumerate(requested_models, start=1):
        overrides = dict(shared_overrides)
        resolved_model: Optional[Path] = None

        if model_path is not None:
            resolved_model = model_path
            if not resolved_model.is_absolute():
                resolved_model = (PROJECT_ROOT / resolved_model).resolve()
            if not resolved_model.exists():
                raise FileNotFoundError(f"Model file not found: {resolved_model}")
            overrides["path"] = resolved_model

        recognizer = GestureRecognizer(config_path, model_overrides=overrides or None)
        metadata = recognizer.model_metadata

        display_name = metadata.get("model_type") if metadata else None
        if isinstance(display_name, str) and display_name:
            display_name = display_name.replace("_", " ")
        elif resolved_model is not None:
            display_name = resolved_model.stem
        else:
            resolved_default = recognizer.model_path
            display_name = resolved_default.stem if resolved_default else f"config default #{index}"

        options.append(
            DebugModelOption(
                recognizer=recognizer,
                name=str(display_name),
                path=resolved_model,
                metadata=metadata,
            )
        )

    return options


def _extract_overall_score(metadata: Dict[str, Any]) -> Optional[str]:
    report = metadata.get("report") if isinstance(metadata, dict) else None
    if not isinstance(report, dict):
        return None

    overall = report.get("overall")
    candidates: List[Any] = []
    if isinstance(overall, dict):
        for key in ("f1-score", "f1_score", "f1", "accuracy"):
            if key in overall:
                candidates.append(overall[key])
    if "accuracy" in report and report["accuracy"] not in candidates:
        candidates.append(report["accuracy"])

    for value in candidates:
        if value is None:
            continue
        try:
            return f"{float(value):0.2f}"
        except (TypeError, ValueError):
            return str(value)
    return None


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
    classifier = recognizer.classifier
    feature_extractor = getattr(recognizer, "_feature_extractor", None)
    if classifier is None or feature_extractor is None:
        return ["Classifier unavailable"]

    features = feature_extractor.extract(list(landmarks), handed_label)
    if features is None:
        return ["Feature extraction failed"]

    predict_proba = getattr(classifier, "predict_proba", None)
    base_classifier = getattr(classifier, "_classifier", None)
    classes = getattr(classifier, "classes_", None)

    if predict_proba is None and base_classifier is not None:
        predict_proba = getattr(base_classifier, "predict_proba", None)
        classes = getattr(base_classifier, "classes_", classes)

    if predict_proba is None or classes is None:
        return ["Classifier lacks probability support"]

    try:
        proba_row = predict_proba([features])[0]
    except Exception as exc:  # pragma: no cover - defensive
        return [f"predict_proba error: {exc}"]

    try:
        proba_iter = list(float(score) for score in proba_row)
    except Exception:  # pragma: no cover - fallback
        return ["Probability output unrecognized"]

    label_encoder = getattr(classifier, "_label_encoder", None) or getattr(recognizer, "_label_encoder", None)

    indexed = sorted(((score, idx) for idx, score in enumerate(proba_iter)), reverse=True)
    top = indexed[:3]
    lines: list[str] = []
    for score, idx in top:
        try:
            encoded = classes[idx]
        except Exception:
            encoded = idx
        if label_encoder is not None:
            try:
                label = label_encoder.inverse_transform([encoded])[0]
            except Exception:
                label = str(encoded)
        else:
            label = str(encoded)
        lines.append(f"{label}: {score:0.2f}")
    return lines if lines else ["No classes"]


def main() -> None:
    args = parse_args()

    try:
        model_options = _build_model_options(args)
    except Exception as exc:  # pragma: no cover - surface initialization errors
        raise RuntimeError(f"Failed to initialize gesture recognizers: {exc}") from exc

    if not model_options:
        raise RuntimeError("No gesture models could be initialized for debugging.")

    print("Loaded gesture models for debugging:")
    for idx, option in enumerate(model_options, start=1):
        resolved_path = option.resolved_path
        path_display = str(resolved_path) if resolved_path else "(using config path)"
        metadata = option.metadata or {}
        summary_bits: List[str] = []
        model_type = metadata.get("model_type") if isinstance(metadata, dict) else None
        if isinstance(model_type, str) and model_type:
            summary_bits.append(f"type={model_type}")
        samples = metadata.get("samples") if isinstance(metadata, dict) else None
        if samples:
            summary_bits.append(f"samples={samples}")
        score = _extract_overall_score(metadata) if metadata else None
        if score is not None:
            summary_bits.append(f"score={score}")
        if not summary_bits:
            summary_bits.append("no metadata")
        print(f"  [{idx}] {option.name}: {path_display} ({', '.join(summary_bits)})")

    if len(model_options) > 1:
        print("Press 'm' in the preview window to cycle between loaded models.")

    active_index = 0
    recognizer = model_options[active_index].recognizer
    if not recognizer.enabled:
        print("WARNING: Gesture classifier not loaded. Check the model path in gestures.yml or CLI overrides.")

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
            active_option = model_options[active_index]
            recognizer = active_option.recognizer

            success, frame = capture.read()
            if not success:
                print("Warning: failed to read frame from camera")
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            start_ts = time.perf_counter()
            events, overlays = recognizer.process(
                results.multi_hand_landmarks,
                results.multi_handedness,
            )
            duration = time.perf_counter() - start_ts
            active_option.stats.record(duration)

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
                "[Gesture Debug] press Q or ESC to exit" + (
                    " | press M to cycle models" if len(model_options) > 1 else ""
                ),
                f"Hands detected: {hand_count}",
                f"Model slot {active_index + 1}/{len(model_options)}: {active_option.name}",
                f"Model loaded: {'yes' if recognizer.enabled else 'NO'}",
            ]

            model_path = active_option.resolved_path
            if model_path:
                header_lines.append(f"Model file: {model_path.name}")

            metadata = active_option.metadata
            if metadata:
                model_type = metadata.get("model_type")
                if model_type:
                    header_lines.append(f"Model type: {model_type}")
                score = _extract_overall_score(metadata)
                if score is not None:
                    header_lines.append(f"Hold-out score: {score}")

            stats = active_option.stats
            last_duration = stats.last_duration
            recent_avg = stats.recent_average
            if last_duration is not None:
                last_ms = last_duration * 1000.0
                if recent_avg is not None and recent_avg > 0.0:
                    recent_ms = recent_avg * 1000.0
                    est_fps = 1.0 / recent_avg
                    header_lines.append(
                        f"Latency: last={last_ms:0.2f} ms avg={recent_ms:0.2f} ms (~{est_fps:0.1f} FPS)"
                    )
                else:
                    header_lines.append(f"Latency: last={last_ms:0.2f} ms")
            elif stats.frame_count:
                overall = stats.overall_average or 0.0
                header_lines.append(f"Latency: avg={overall * 1000.0:0.2f} ms")

            prob_threshold = getattr(recognizer, "_probability_threshold", None)
            if prob_threshold is not None:
                header_lines.append(f"Confidence threshold: {prob_threshold:0.2f}")

            smoothing = getattr(recognizer, "_smoothing_window", None)
            min_consensus = getattr(recognizer, "_min_consensus", None)
            max_history = getattr(recognizer, "_max_history", None)
            smoothing_bits = []
            if smoothing is not None:
                smoothing_bits.append(f"window={smoothing}")
            if min_consensus is not None:
                smoothing_bits.append(f"min_consensus={min_consensus}")
            if max_history is not None:
                smoothing_bits.append(f"max_history={max_history}")
            if smoothing_bits:
                header_lines.append("Smoothing: " + ", ".join(smoothing_bits))

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
                append_log(args.save_log, f"{active_option.name} | {status}")
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
            if key in (ord("m"), ord("M")) and len(model_options) > 1:
                previous_option = model_options[active_index]
                active_index = (active_index + 1) % len(model_options)
                model_options[active_index].recognizer.reset()
                prev_stats = previous_option.stats
                if prev_stats.frame_count:
                    avg_ms = (prev_stats.overall_average or 0.0) * 1000.0
                    print(
                        f"[{previous_option.name}] captured {prev_stats.frame_count} frames; "
                        f"avg latency {avg_ms:0.2f} ms, max {prev_stats.max_duration * 1000.0:0.2f} ms"
                    )
                print(
                    f"Switched to model [{active_index + 1}/{len(model_options)}] "
                    f"{model_options[active_index].name}"
                )
                continue

    finally:
        hands.close()
        capture.release()
        cv2.destroyWindow(window_name)
        print("\nLatency summary by model:")
        for option in model_options:
            stats = option.stats
            if stats.frame_count:
                avg_ms = (stats.overall_average or 0.0) * 1000.0
                recent_ms = (stats.recent_average or 0.0) * 1000.0 if stats.recent_average else None
                max_ms = stats.max_duration * 1000.0
                summary = (
                    f"  - {option.name}: frames={stats.frame_count}, "
                    f"avg={avg_ms:0.2f} ms"
                )
                if recent_ms is not None:
                    summary += f", recent_avg={recent_ms:0.2f} ms"
                summary += f", max={max_ms:0.2f} ms"
                print(summary)
            else:
                print(f"  - {option.name}: no frames captured")


if __name__ == "__main__":
    main()
