from __future__ import annotations

import logging
import math
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union, cast

import yaml

if TYPE_CHECKING:  # pragma: no cover - import hints only during type-checking
    import joblib as joblib_type
    import numpy as np_type

try:  # Optional heavy dependencies are imported lazily when available
    import joblib
except ImportError:  # pragma: no cover - handled gracefully at runtime
    joblib = None  # type: ignore[assignment]

try:  # numpy is optional but useful for ML workflows
    import numpy as np
except ImportError:  # pragma: no cover - handled gracefully at runtime
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GestureActionConfig:
    """Configuration describing how a gesture label maps to a teleop event."""

    label: str
    event: str
    hands_required: int = 1
    hold_frames: int = 5
    allowed_hands: Optional[List[str]] = None
    overlay: Optional[str] = None

    def normalized_allowed_hands(self) -> Optional[List[str]]:
        if not self.allowed_hands:
            return None
        return [hand.capitalize() for hand in self.allowed_hands]


@dataclass
class HandPrediction:
    """Smoothed gesture prediction for a single hand."""

    label: Optional[str]
    confidence: float


@dataclass
class GestureEvent:
    """Gesture state change produced by the recognizer."""

    change: str  # "start" or "end"
    event: str
    label: str
    confidence: float
    overlay: Optional[str] = None


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[0]


def load_gesture_config(config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load the YAML configuration describing the gesture recognizer."""

    project_root = _default_project_root()
    candidate = (
        Path(config_path)
        if config_path
        else project_root / "gestures.yml"
    )
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve()

    config: Dict[str, Any]
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    else:
        logger.warning("Gesture config not found at %s. Using defaults.", candidate)
        config = {}

    model_cfg: Dict[str, Any] = dict(config.get("model", {}) or {})
    model_cfg.setdefault("path", "models/gesture_classifier.joblib")
    model_cfg.setdefault("probability_threshold", 0.6)
    model_cfg.setdefault("smoothing_window", 5)
    model_cfg.setdefault("min_consensus", max(1, int(model_cfg.get("smoothing_window", 5)) // 2 + 1))
    model_cfg.setdefault("max_history", max(int(model_cfg.get("smoothing_window", 5)) * 3, 15))

    gesture_items: List[Dict[str, Any]] = list(config.get("gestures", []) or [])
    if not isinstance(gesture_items, list):
        raise ValueError("gestures section in config must be a list")

    return {
        "config_path": candidate,
        "model": model_cfg,
        "gestures": gesture_items,
    }


class GestureActionManager:
    """Tracks gesture state transitions with temporal debouncing."""

    def __init__(self, configs: Iterable[GestureActionConfig]):
        self._configs: List[GestureActionConfig] = list(configs)
        self._hold_counts: Dict[str, int] = {cfg.event: 0 for cfg in self._configs}
        self._active_events: Dict[str, GestureActionConfig] = {}

    def update(self, predictions: Dict[str, HandPrediction]) -> List[GestureEvent]:
        events: List[GestureEvent] = []
        for cfg in self._configs:
            matches = self._matching_hands(cfg, predictions)
            is_active = cfg.event in self._active_events

            if matches:
                self._hold_counts[cfg.event] = min(self._hold_counts[cfg.event] + 1, cfg.hold_frames + 1)
            else:
                self._hold_counts[cfg.event] = 0

            if not is_active and matches and self._hold_counts[cfg.event] >= cfg.hold_frames:
                confidence = self._aggregate_confidence(matches, cfg.hands_required)
                events.append(
                    GestureEvent(
                        change="start",
                        event=cfg.event,
                        label=cfg.label,
                        confidence=confidence,
                        overlay=cfg.overlay,
                    )
                )
                self._active_events[cfg.event] = cfg
            elif is_active and not matches:
                prev_cfg = self._active_events.pop(cfg.event)
                events.append(
                    GestureEvent(
                        change="end",
                        event=prev_cfg.event,
                        label=prev_cfg.label,
                        confidence=0.0,
                        overlay=prev_cfg.overlay,
                    )
                )
        return events

    def _matching_hands(
        self, cfg: GestureActionConfig, predictions: Dict[str, HandPrediction]
    ) -> List[Tuple[str, HandPrediction]]:
        allowed = cfg.normalized_allowed_hands()
        matched: List[Tuple[str, HandPrediction]] = []
        for hand_label, prediction in predictions.items():
            if prediction.label != cfg.label:
                continue
            if allowed is not None and hand_label.capitalize() not in allowed:
                continue
            matched.append((hand_label.capitalize(), prediction))

        if cfg.hands_required <= 1:
            return matched[:1] if matched else []

        if allowed:
            if all(any(hand == needed for hand, _ in matched) for needed in allowed):
                return [(hand, pred) for hand, pred in matched if hand in allowed]
            return []

        return matched if len(matched) >= cfg.hands_required else []

    @staticmethod
    def _aggregate_confidence(
        matches: List[Tuple[str, HandPrediction]], hands_required: int
    ) -> float:
        if not matches:
            return 0.0
        if hands_required <= 1:
            return matches[0][1].confidence
        return sum(pred.confidence for _, pred in matches) / len(matches)

    def reset(self) -> None:
        self._hold_counts = {cfg.event: 0 for cfg in self._configs}
        self._active_events.clear()


class GestureFeatureExtractor:
    """Converts raw landmarks to a normalized feature vector for classification."""

    _ANCHOR_INDICES = (5, 9, 13, 17)

    def extract(self, landmarks: Sequence[object], handedness_label: str) -> Optional[List[float]]:
        if landmarks is None or len(landmarks) < 21:
            return None

        try:
            wrist = landmarks[0]
        except (IndexError, TypeError):
            return None

        base_scale = self._compute_scale(landmarks, wrist)
        if base_scale <= 1e-6:
            return None

        features: List[float] = []
        for lm in landmarks:
            dx = (getattr(lm, "x", 0.0) - getattr(wrist, "x", 0.0)) / base_scale
            dy = (getattr(lm, "y", 0.0) - getattr(wrist, "y", 0.0)) / base_scale
            dz = (getattr(lm, "z", 0.0) - getattr(wrist, "z", 0.0)) / base_scale
            features.extend((dx, dy, dz))

        hand_flag = 1.0 if handedness_label.lower() == "left" else 0.0
        features.append(hand_flag)
        return features

    def _compute_scale(self, landmarks: Sequence[object], wrist: object) -> float:
        distances: List[float] = []
        wx = getattr(wrist, "x", 0.0)
        wy = getattr(wrist, "y", 0.0)
        wz = getattr(wrist, "z", 0.0)
        for idx in self._ANCHOR_INDICES:
            try:
                anchor = landmarks[idx]
            except (IndexError, TypeError):
                continue
            dx = getattr(anchor, "x", 0.0) - wx
            dy = getattr(anchor, "y", 0.0) - wy
            dz = getattr(anchor, "z", 0.0) - wz
            distances.append(math.sqrt(dx * dx + dy * dy + dz * dz))
        if not distances:
            return 1.0
        return max(sum(distances) / len(distances), 1e-3)


class BaseGestureClassifier:
    def predict(self, features: Sequence[float]) -> Tuple[Optional[str], float]:
        raise NotImplementedError


class MLGestureClassifier(BaseGestureClassifier):
    """Wrapper around a scikit-learn classifier saved via joblib."""

    def __init__(self, model_path: Path):
        if joblib is None:
            raise ImportError("joblib is required to load the gesture model")
        if not model_path.exists():
            raise FileNotFoundError(f"Gesture model not found at {model_path}")

        payload = joblib.load(model_path)
        try:
            self._classifier = payload["classifier"]
            self._label_encoder = payload["label_encoder"]
            self.feature_names = payload.get("feature_names")
        except KeyError as exc:  # pragma: no cover - guard for unexpected payloads
            raise ValueError("Invalid gesture model payload") from exc

        self.model_path: Path = model_path
        self.metadata: Dict[str, Any] = payload.get("metadata", {}) if isinstance(payload, dict) else {}

        if np is None:
            logger.warning("numpy not available – falling back to Python lists for predictions")

    def predict(self, features: Sequence[float]) -> Tuple[Optional[str], float]:
        if not features:
            return None, 0.0
        proba = self._classifier.predict_proba([features])[0]
        proba_values = proba.tolist() if hasattr(proba, "tolist") else list(proba)
        if not proba_values:
            return None, 0.0
        best_index = max(range(len(proba_values)), key=lambda idx: proba_values[idx])
        encoded_class = self._classifier.classes_[best_index]
        label = self._label_encoder.inverse_transform([encoded_class])[0]
        return str(label), float(proba_values[best_index])

    def predict_proba(self, feature_matrix: Sequence[Sequence[float]]):
        return self._classifier.predict_proba(feature_matrix)

    @property
    def classes_(self):
        return self._classifier.classes_


def _resolve_model_reference(reference: Union[str, Path]) -> Optional[Path]:
    candidate = Path(reference)
    if not candidate.suffix:
        models_dir = _default_project_root() / "models"
        if not models_dir.exists():
            return None
        alias = str(reference).lower()
        try:
            ranked = sorted(
                (p for p in models_dir.glob("*.joblib") if alias in p.stem.lower()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        if ranked:
            return ranked[0].resolve()
        return None

    if not candidate.is_absolute():
        candidate = (_default_project_root() / candidate).resolve()
    return candidate if candidate.exists() else None


class GestureRecognizer:
    """High-level gesture recognizer that wraps classification + gesture actions."""

    def __init__(
        self,
        config_path: Optional[Path | str] = None,
        *,
        model: Optional[Union[str, Path]] = None,
        model_overrides: Optional[Mapping[str, Any]] = None,
    ):
        self._config = load_gesture_config(config_path)
        model_cfg_raw = self._config.get("model", {})
        model_cfg = dict(cast(Dict[str, Any], model_cfg_raw))

        effective_overrides: Dict[str, Any] = {}
        if model is not None:
            resolved = _resolve_model_reference(model)
            if resolved is None:
                logger.warning("Gesture model override '%s' could not be resolved.", model)
            else:
                effective_overrides["path"] = str(resolved)

        if model_overrides:
            for key, value in model_overrides.items():
                if value is not None:
                    effective_overrides[str(key)] = value

        for key, value in effective_overrides.items():
            model_cfg[str(key)] = value

        self._probability_threshold: float = float(model_cfg.get("probability_threshold", 0.6))
        self._smoothing_window: int = max(1, int(model_cfg.get("smoothing_window", 5)))
        self._min_consensus: int = max(1, int(model_cfg.get("min_consensus", max(1, self._smoothing_window // 2 + 1))))
        self._max_history: int = max(int(model_cfg.get("max_history", self._smoothing_window * 3)), self._smoothing_window)

        self._feature_extractor = GestureFeatureExtractor()
        self._hand_history: Dict[str, Deque[Optional[str]]] = {}
        self._hand_scores: Dict[str, Deque[float]] = {}
        self._warned_missing_model = False

        model_path = Path(model_cfg.get("path", "models/gesture_classifier.joblib"))
        if not model_path.is_absolute():
            model_path = (_default_project_root() / model_path).resolve()

        classifier: Optional[BaseGestureClassifier]
        try:
            classifier = MLGestureClassifier(model_path)
        except (ImportError, FileNotFoundError) as exc:
            classifier = None
            logger.warning(
                "Gesture classifier unavailable (%s). Gestures will be disabled until a model is trained.",
                exc,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            classifier = None
            logger.error("Failed to load gesture classifier: %s", exc)

        self._classifier = classifier
        self._label_encoder = getattr(classifier, "_label_encoder", None) if classifier else None
        self._model_metadata: Dict[str, Any] = getattr(classifier, "metadata", {}) if classifier else {}
        self._model_path: Optional[Path] = getattr(classifier, "model_path", model_path)

        gestures_raw = self._config.get("gestures", [])
        gesture_list: List[Dict[str, Any]] = (
            list(gestures_raw) if isinstance(gestures_raw, list) else []
        )

        action_configs: List[GestureActionConfig] = []
        for item in gesture_list:
            label_value = item.get("label")
            event_value = item.get("event")
            if not isinstance(label_value, str) or not isinstance(event_value, str):
                continue
            hands_required = int(item.get("hands_required", 1))
            hold_frames = max(1, int(item.get("hold_frames", self._smoothing_window)))
            allowed_hands_value = item.get("allowed_hands")
            if isinstance(allowed_hands_value, list):
                allowed_hands = [str(hand) for hand in allowed_hands_value]
            else:
                allowed_hands = None
            overlay_text = item.get("overlay")
            if overlay_text is not None and not isinstance(overlay_text, str):
                overlay_text = str(overlay_text)
            action_configs.append(
                GestureActionConfig(
                    label=label_value,
                    event=event_value,
                    hands_required=hands_required,
                    hold_frames=hold_frames,
                    allowed_hands=allowed_hands,
                    overlay=overlay_text,
                )
            )
        self._action_manager = GestureActionManager(action_configs)

    @property
    def enabled(self) -> bool:
        return self._classifier is not None

    @property
    def classifier(self) -> Optional[BaseGestureClassifier]:
        return self._classifier

    @property
    def label_encoder(self):
        return getattr(self, "_label_encoder", None)

    @property
    def model_metadata(self) -> Dict[str, Any]:
        return dict(self._model_metadata)

    @property
    def model_path(self) -> Optional[Path]:
        return self._model_path

    def reset(self) -> None:
        self._hand_history.clear()
        self._hand_scores.clear()
        self._action_manager.reset()

    def process(
        self,
        hand_landmarks: Optional[Sequence[object]],
        handedness_list: Optional[Sequence[object]],
    ) -> Tuple[List[GestureEvent], List[str]]:
        overlays: List[str] = []

        if self._classifier is None:
            if not self._warned_missing_model:
                overlays.append("Gesture model not loaded. Run training to enable gestures.")
                self._warned_missing_model = True
            events = self._action_manager.update({})
            if events:
                overlays.append("Clearing active gesture events")
            return events, overlays

        if not hand_landmarks or not handedness_list:
            events = self._action_manager.update({})
            if events:
                overlays.append("Gestures cleared")
            return events, overlays

        predictions: Dict[str, HandPrediction] = {}

        for landmarks, handedness in zip(hand_landmarks, handedness_list):
            try:
                label = handedness.classification[0].label  # type: ignore[attr-defined]
            except (IndexError, AttributeError):
                continue
            if hasattr(landmarks, "landmark"):
                landmarks_seq = list(getattr(landmarks, "landmark"))
            elif isinstance(landmarks, Sequence):
                landmarks_seq = list(landmarks)
            else:
                landmarks_seq = []

            features = self._feature_extractor.extract(landmarks_seq, label)
            predicted_label: Optional[str]
            confidence: float
            if features is None:
                predicted_label = None
                confidence = 0.0
            else:
                raw_label, raw_confidence = self._classifier.predict(features)
                if raw_label is None or raw_confidence < self._probability_threshold:
                    predicted_label = None
                    confidence = raw_confidence
                else:
                    predicted_label, confidence = raw_label, raw_confidence

            smoothed_label, smoothed_confidence = self._update_hand_history(
                label, predicted_label, confidence
            )
            predictions[label.capitalize()] = HandPrediction(smoothed_label, smoothed_confidence)
            overlays.append(
                f"{label.capitalize()}: {(smoothed_label or '—')} ({smoothed_confidence:0.2f})"
            )

        events = self._action_manager.update(predictions)
        return events, overlays

    def _update_hand_history(
        self, hand_label: str, predicted_label: Optional[str], confidence: float
    ) -> Tuple[Optional[str], float]:
        history = self._hand_history.setdefault(
            hand_label, deque(maxlen=self._max_history)
        )
        scores = self._hand_scores.setdefault(hand_label, deque(maxlen=self._max_history))
        history.append(predicted_label)
        scores.append(confidence)

        if self._smoothing_window <= 1:
            return predicted_label, confidence

        recent_labels = list(history)[-self._smoothing_window :]
        recent_scores = list(scores)[-self._smoothing_window :]
        counts = Counter(lbl for lbl in recent_labels if lbl)
        if not counts:
            return None, 0.0
        best_label, best_count = counts.most_common(1)[0]
        if best_count < self._min_consensus:
            return None, 0.0
        relevant_scores = [
            score for lbl, score in zip(recent_labels, recent_scores) if lbl == best_label
        ]
        avg_score = sum(relevant_scores) / len(relevant_scores) if relevant_scores else 0.0
        return best_label, avg_score
