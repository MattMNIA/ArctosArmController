"""Strategy for keeping a detected object centered in the camera frame."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency for visualization
    cv2 = None  # type: ignore[assignment]

try:  # Optional dependencies for gesture recognition
    import mediapipe as mp
except ImportError:  # pragma: no cover - optional dependency for gesture recognition
    mp = None  # type: ignore[assignment]

import numpy as np

from ..calibration.object_centering import (
    AxisCalibration,
    DEFAULT_CALIBRATION_PATH,
    ObjectCenteringCalibration,
    load_calibration,
)
from ..detectors.base_detector import BaseDetector, Detection, DetectionResult
from ..detectors.gesture.gesture_recognizer import GestureRecognizer
from ...motion_service import JointCommand, MotionService

logger = logging.getLogger(__name__)
_DEG_TO_RAD = math.pi / 180.0


class ArmDriverProtocol(Protocol):
    """Subset of the driver interface required by the centering strategy."""

    def get_feedback(self) -> Dict[str, Any]:  # pragma: no cover - Protocol definition
        ...

    def send_joint_targets(self, q: List[float], t_s: Optional[float] = None) -> None:  # pragma: no cover - Protocol definition
        ...

    def start_joint_velocity(self, joint_index: int, scale: float) -> None:  # pragma: no cover - Protocol definition
        ...

    def stop_joint_velocity(self, joint_index: int) -> None:  # pragma: no cover - Protocol definition
        ...


@dataclass
class AxisError:
    """Stores the pixel error and resulting velocity scale for one axis."""

    error_pixels: float
    velocity_scale: float
    joint_indices: list[int]  # Changed to support multiple joints

    def as_dict(self) -> Dict[str, Any]:
        return {
            "error_pixels": float(self.error_pixels),
            "velocity_scale": float(self.velocity_scale),
            "joint_indices": self.joint_indices,  # Updated
        }


class TargetSelector:
    """Chooses which detection to track based on label preferences and confidence."""

    def __init__(
        self,
        preferred_labels: Optional[Sequence[str]] = None,
        *,
        min_confidence: float = 0.3,
        lock_on: bool = True,
    ) -> None:
        self._preferred_labels = {label.lower() for label in preferred_labels or []}
        self._min_confidence = max(0.0, float(min_confidence))
        self._lock_on = lock_on
        self._active_label: Optional[str] = None

    def set_preferred_labels(self, labels: Optional[Sequence[str]]) -> None:
        self._preferred_labels = {label.lower() for label in labels or []}
        if not self._preferred_labels:
            self._active_label = None

    def set_single_label(self, label: Optional[str]) -> None:
        if label is None:
            self._preferred_labels = set()
            self._active_label = None
            return
        normalized = label.lower()
        self._preferred_labels = {normalized}
        self._active_label = None

    def clear_lock(self) -> None:
        self._active_label = None

    def select(self, detections: Sequence[Detection]) -> Optional[Detection]:
        candidates = [d for d in detections if d.confidence >= self._min_confidence]
        if not candidates:
            return None

        if self._active_label:
            locked = self._best_label_match(candidates, {self._active_label})
            if locked:
                return locked
            self._active_label = None

        if self._preferred_labels:
            preferred = self._best_label_match(candidates, self._preferred_labels)
            if preferred:
                if self._lock_on:
                    self._active_label = preferred.label.lower()
                return preferred
            return None

        fallback = max(candidates, key=self._score_detection)
        if self._lock_on:
            self._active_label = fallback.label.lower()
        return fallback

    @staticmethod
    def _score_detection(detection: Detection) -> Tuple[float, float]:
        bbox = detection.bbox
        area = bbox.width * bbox.height
        return (detection.confidence, area)

    @staticmethod
    def _best_label_match(
        detections: Sequence[Detection],
        labels: Iterable[str],
    ) -> Optional[Detection]:
        label_set = {label.lower() for label in labels}
        labeled = [d for d in detections if d.label.lower() in label_set]
        if not labeled:
            return None
        return max(labeled, key=lambda d: (d.confidence, d.bbox.width * d.bbox.height))


class ObjectCenteringStrategy:
    """Continuously adjusts arm joints to keep a selected object centered."""

    def __init__(
        self,
        detector: BaseDetector,
        *,
        motion_service: Optional[MotionService] = None,
        driver: Optional[ArmDriverProtocol] = None,
        calibration: Optional[ObjectCenteringCalibration] = None,
        calibration_path: Optional[Path | str] = None,
        preferred_labels: Optional[Sequence[str]] = None,
        min_confidence: float = 0.3,
        command_interval: float = 0.3,
        move_duration: float = 0.4,
        use_motion_queue: bool = False,
        display_feed: bool = False,
        display_window_name: Optional[str] = None,
        invert_horizontal: bool = False,
        invert_vertical: bool = False,
        satisfied_error_pixels: float = 64.0,
        satisfied_duration: float = 4.0,
        latency_compensation_s: float = 0.05,
        latency_slowdown: float = 2.5,
        prediction_limit_px: float = 180.0,
        error_filter_alpha: float = 0.4,
        swing_damping_factor: float = 0.6,
        swing_window: int = 6,
        swing_tolerance_px: float = 6.0,
        min_command_delay_s: float = 3.0,
        require_new_frame: bool = True,
        frame_wait_tolerance: float = 0.02,
        velocity_gain: float = 0.5,
        max_velocity: float = 1.0,
        detection_buffer_frames: int = 3,
        detection_timeout_s: float = 0.5,
        enable_gestures: bool = True,
        gesture_config_path: Optional[Path | str] = None,
    ) -> None:
        if calibration is None:
            candidate_path = Path(calibration_path) if calibration_path is not None else DEFAULT_CALIBRATION_PATH
            try:
                calibration = load_calibration(candidate_path)
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "ObjectCenteringStrategy requires calibration data; run the calibration script first."
                ) from exc
        calibration.ensure_complete()

        if motion_service is None and driver is None:
            raise ValueError("Either a MotionService or a driver instance must be provided")
        if use_motion_queue and motion_service is None:
            raise ValueError("use_motion_queue=True requires a MotionService instance")

        self._detector = detector
        self._motion_service = motion_service
        self._driver = driver or (motion_service.driver if motion_service else None)
        self._calibration = calibration
        self._selector = TargetSelector(preferred_labels, min_confidence=min_confidence)
        self._command_interval = max(0.05, float(command_interval))
        self._move_duration = max(0.1, float(move_duration))
        self._use_motion_queue = use_motion_queue
        self._invert_horizontal = bool(invert_horizontal)
        self._invert_vertical = bool(invert_vertical)
        self._satisfied_error_pixels = max(0.0, float(satisfied_error_pixels))
        self._satisfied_duration = max(0.0, float(satisfied_duration))
        self._satisfied_since: Optional[float] = None
        self._active_target: Optional[Detection] = None
        self._latency_compensation_s = max(0.0, float(latency_compensation_s))
        self._latency_slowdown = max(0.0, float(latency_slowdown))
        self._prediction_limit_px = max(0.0, float(prediction_limit_px))
        self._prev_error_timestamp: Optional[float] = None
        self._prev_error_x: Optional[float] = None
        self._prev_error_y: Optional[float] = None
        self._last_latency = 0.0
        self._last_latency_scale = 1.0
        self._error_filter_alpha = min(max(float(error_filter_alpha), 0.0), 1.0)
        self._filtered_error_x: Optional[float] = None
        self._filtered_error_y: Optional[float] = None
        self._swing_damping_factor = max(0.0, float(swing_damping_factor))
        self._swing_window = max(2, int(swing_window))
        self._swing_tolerance_px = max(0.0, float(swing_tolerance_px))
        self._swing_history_x: Deque[int] = deque(maxlen=self._swing_window)
        self._swing_history_y: Deque[int] = deque(maxlen=self._swing_window)
        self._current_swing_scale = 1.0
        self._last_total_scale = 1.0
        self._min_command_delay = max(0.0, float(min_command_delay_s))
        self._next_command_time = 0.0
        self._require_new_frame = bool(require_new_frame)
        self._frame_wait_tolerance = max(0.0, float(frame_wait_tolerance))
        self._velocity_gain = max(0.0, float(velocity_gain))
        self._max_velocity = max(0.0, float(max_velocity))
        self._await_new_frame = False
        self._last_command_frame_ts: Optional[float] = None

        # Detection buffering for smoother tracking
        self._detection_buffer_frames = max(1, int(detection_buffer_frames))
        self._detection_timeout_s = max(0.1, float(detection_timeout_s))
        self._detection_buffer: Deque[Tuple[Detection, float]] = deque(maxlen=self._detection_buffer_frames)
        self._last_detection_time: Optional[float] = None

        # PID controllers for each axis
        # PID Tuning Guide:
        # - Kp (Proportional): Controls responsiveness. Increase for faster response, decrease for stability.
        # - Ki (Integral): Eliminates steady-state error. Increase if it doesn't settle on target, decrease if oscillating.
        # - Kd (Derivative): Dampens oscillations. Increase if swaying/overshooting, decrease if too sluggish.
        # - Start with Ki=0, Kd=0, tune Kp until it oscillates, then add Kd to stabilize, finally Ki for precision.
        # - Monitor logs for scale values; adjust gains in small increments (e.g., 0.001-0.01).
        self._pid_horizontal = {
            'kp': 0.01,  # Reduced from 0.02 to reduce oscillations
            'ki': 0.001,  # Reduced from 0.002 to prevent instability
            'kd': 0.008,  # Increased from 0.006 to better dampen oscillations
            'integral': 0.0,
            'prev_error': 0.0,
            'prev_time': time.time(),
            'integral_max': 1.0  # anti-windup
        }
        self._pid_vertical = {
            'kp': 0.12,  # Slightly reduced from 0.15 to reduce overshoot
            'ki': 0.0003,  # Reduced from 0.001 to prevent integral windup that causes slowdown before centering
            'kd': 0.015,  # Increased from 0.005 to dampen oscillations when reaching target
            'integral': 0.0,
            'prev_error': 0.0,
            'prev_time': time.time(),
            'integral_max': 0.5  # Reduced from 1.0 to limit integral windup
        }

        if display_feed and cv2 is None:
            logger.warning("display_feed requested but OpenCV is not available; disabling preview")
            display_feed = False
        self._display_feed = bool(display_feed)
        self._display_window_name = display_window_name or "Object Centering"
        self._display_initialized = False

        # Gesture recognition setup
        self._enable_gestures = bool(enable_gestures) and mp is not None
        if self._enable_gestures and mp is None:
            logger.warning("enable_gestures requested but mediapipe is not available; disabling gestures")
            self._enable_gestures = False
        self._gesture_recognizer: Optional[GestureRecognizer] = None
        self._hands: Optional[Any] = None
        if self._enable_gestures and mp is not None:
            try:
                self._gesture_recognizer = GestureRecognizer(config_path=gesture_config_path, model="mlp")
                self._hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                logger.info(f"Gesture recognition enabled (classifier loaded: {self._gesture_recognizer.enabled})")
            except Exception as exc:
                logger.warning("Failed to initialize gesture recognition: %s", exc)
                self._enable_gestures = False
        self._paused = False
        self._last_gesture_process_time = 0.0
        self._gesture_process_interval = 0.15  # Only process gestures every 150ms to reduce CPU load

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._last_command_time = 0.0
        self._last_status: Dict[str, Any] = {}
        self._last_axis_errors: List[AxisError] = []
        self._last_gesture_overlays: List[str] = []
        self._last_hand_landmarks: Optional[List[Any]] = None
        self._last_handedness: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Public API
    def start(self, *, poll_interval: float = 0.05) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._dt = max(0.0, float(poll_interval))
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run_loop,
            args=(max(0.0, float(poll_interval)),),
            name="object-centering",
            daemon=True,
        )
        self._worker.start()
        self._detector.start(poll_interval=poll_interval)
        logger.info(f"Object centering strategy started (gestures {'enabled' if self._enable_gestures else 'disabled'})")

    def stop(self) -> None:
        self._stop_event.set()
        self._detector.stop()
        if self._worker:
            self._worker.join(timeout=1.0)
        self._worker = None
        logger.info("Object centering strategy stopped")
        self._close_display_window()

    def step(self) -> Optional[Dict[str, Any]]:
        result = self._detector.detect(return_frame=True)
        if result is None:
            self._last_axis_errors = []
            self._record_status({"state": "no_frame"})
            return None

        latency = time.time() - result.timestamp
        logger.debug(f"Object centering latency: {latency:.3f}s")

        # Process gestures if enabled
        if self._enable_gestures and result.frame is not None and self._hands is not None and self._gesture_recognizer is not None:
            self._process_gestures(result.frame)
        elif self._enable_gestures:
            logger.debug("Gesture processing skipped: missing frame or uninitialized components")

        # If paused, skip centering logic
        if self._paused:
            self._last_axis_errors = []
            self._maybe_display_frame(result, None, None, None, [])
            self._record_status({"state": "paused", "timestamp": result.timestamp})
            return {"state": "paused", "timestamp": result.timestamp}

        if result.frame is None or not result.detections:
            # Check if we have buffered detections to use
            buffered_detection = self._get_buffered_detection()
            if buffered_detection is not None:
                logger.debug(f"Using buffered detection from {time.time() - buffered_detection[1]:.3f}s ago")
                detection = buffered_detection[0]
                # Use the buffered detection but mark that we're using old data
                self._active_target = detection
                frame = result.frame if result.frame is not None else self._get_last_frame()
                if frame is None:
                    self._last_axis_errors = []
                    self._maybe_display_frame(result, None, None, None, [])
                    self._record_status({"state": "no_frame", "timestamp": result.timestamp})
                    self._clear_active_target()
                    return None

                height, width = frame.shape[:2]
                bbox_center = detection.bbox.center()
                error_x = bbox_center[0] - (width / 2.0)
                error_y = bbox_center[1] - (height / 2.0)

                axis_errors = self._compute_axis_errors(error_x, error_y, width, height)
                self._last_axis_errors = axis_errors

                display_axis_errors = axis_errors
                self._maybe_display_frame(
                    result,
                    detection,
                    error_x,
                    error_y,
                    display_axis_errors,
                    None,
                    None,
                )

                velocity_scales = {}
                for axis_error in axis_errors:
                    for joint_index in axis_error.joint_indices:
                        velocity_scales[joint_index] = axis_error.velocity_scale

                payload = {
                    "timestamp": result.timestamp,
                    "target": detection.to_dict(),
                    "errors": {"x_pixels": float(error_x), "y_pixels": float(error_y)},
                    "velocity_scales": velocity_scales,
                    "resolution_scale": {"x": 1.0, "y": 1.0},
                    "satisfied": False,
                    "using_buffer": True,
                }
                self._record_status({"state": "active_buffered", **payload})
                return payload
            else:
                # No buffered detection available, stop movement
                self._last_axis_errors = []
                self._maybe_display_frame(result, None, None, None, [])
                self._record_status({"state": "no_detections", "timestamp": result.timestamp})
                self._clear_active_target()
                return None

        detection = self._selector.select(result.detections)
        if detection is None:
            # Check if we have buffered detections to use
            buffered_detection = self._get_buffered_detection()
            if buffered_detection is not None:
                logger.debug(f"Using buffered detection from {time.time() - buffered_detection[1]:.3f}s ago")
                detection = buffered_detection[0]
                # Use the buffered detection but mark that we're using old data
                self._active_target = detection
                frame = result.frame
                height, width = frame.shape[:2]
                bbox_center = detection.bbox.center()
                error_x = bbox_center[0] - (width / 2.0)
                error_y = bbox_center[1] - (height / 2.0)

                axis_errors = self._compute_axis_errors(error_x, error_y, width, height)
                self._last_axis_errors = axis_errors

                display_axis_errors = axis_errors
                self._maybe_display_frame(
                    result,
                    detection,
                    error_x,
                    error_y,
                    display_axis_errors,
                    None,
                    None,
                )

                velocity_scales = {}
                for axis_error in axis_errors:
                    for joint_index in axis_error.joint_indices:
                        velocity_scales[joint_index] = axis_error.velocity_scale

                payload = {
                    "timestamp": result.timestamp,
                    "target": detection.to_dict(),
                    "errors": {"x_pixels": float(error_x), "y_pixels": float(error_y)},
                    "velocity_scales": velocity_scales,
                    "resolution_scale": {"x": 1.0, "y": 1.0},
                    "satisfied": False,
                    "using_buffer": True,
                }
                self._record_status({"state": "active_buffered", **payload})
                return payload
            else:
                # No buffered detection available, stop movement
                self._last_axis_errors = []
                self._maybe_display_frame(result, None, None, None, [])
                self._record_status(
                    {
                        "state": "no_target",
                        "timestamp": result.timestamp,
                        "detections": [d.to_dict() for d in result.detections],
                    }
                )
                self._clear_active_target()
                return None

        # Add successful detection to buffer
        self._add_to_detection_buffer(detection, result.timestamp)

        self._active_target = detection

        frame = result.frame
        height, width = frame.shape[:2]
        bbox_center = detection.bbox.center()
        error_x = bbox_center[0] - (width / 2.0)
        error_y = bbox_center[1] - (height / 2.0)

        axis_errors = self._compute_axis_errors(error_x, error_y, width, height)
        self._last_axis_errors = axis_errors

        display_axis_errors = axis_errors
        self._maybe_display_frame(
            result,
            detection,
            error_x,
            error_y,
            display_axis_errors,
            None,
            None,
        )

        velocity_scales = {}
        for axis_error in axis_errors:
            for joint_index in axis_error.joint_indices:
                velocity_scales[joint_index] = axis_error.velocity_scale
        
        payload = {
            "timestamp": result.timestamp,
            "target": detection.to_dict(),
            "errors": {"x_pixels": float(error_x), "y_pixels": float(error_y)},
            "velocity_scales": velocity_scales,
            "resolution_scale": {"x": 1.0, "y": 1.0},
            "satisfied": False,
        }
        self._record_status({"state": "active", **payload})
        return payload

    def set_target_label(self, label: Optional[str]) -> None:
        self._selector.set_single_label(label)

    def set_target_labels(self, labels: Optional[Sequence[str]]) -> None:
        self._selector.set_preferred_labels(labels)

    def clear_lock(self) -> None:
        self._selector.clear_lock()

    def reload_calibration(self, path: Optional[Path | str] = None) -> None:
        candidate = Path(path) if path is not None else DEFAULT_CALIBRATION_PATH
        calibration = load_calibration(candidate)
        calibration.ensure_complete()
        with self._lock:
            self._calibration = calibration

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            status = dict(self._last_status)
            status.update({
                "gestures": {
                    "enabled": self._enable_gestures,
                    "paused": self._paused,
                    "available": self._hands is not None and self._gesture_recognizer is not None,
                }
            })
            return status

    def get_pid_values(self) -> Dict[str, Dict[str, float]]:
        """Get current PID values for both axes."""
        with self._lock:
            return {
                "horizontal": {
                    "kp": self._pid_horizontal["kp"],
                    "ki": self._pid_horizontal["ki"],
                    "kd": self._pid_horizontal["kd"],
                },
                "vertical": {
                    "kp": self._pid_vertical["kp"],
                    "ki": self._pid_vertical["ki"],
                    "kd": self._pid_vertical["kd"],
                },
            }

    def set_pid_values(self, axis: str, kp: Optional[float] = None, ki: Optional[float] = None, kd: Optional[float] = None) -> None:
        """Update PID values for the specified axis."""
        with self._lock:
            if axis == "horizontal":
                pid_dict = self._pid_horizontal
            elif axis == "vertical":
                pid_dict = self._pid_vertical
            else:
                raise ValueError(f"Invalid axis: {axis}. Must be 'horizontal' or 'vertical'")

            if kp is not None:
                pid_dict["kp"] = max(0.0, float(kp))
            if ki is not None:
                pid_dict["ki"] = max(0.0, float(ki))
            if kd is not None:
                pid_dict["kd"] = max(0.0, float(kd))

            logger.info(f"Updated {axis} PID: kp={pid_dict['kp']:.4f}, ki={pid_dict['ki']:.4f}, kd={pid_dict['kd']:.4f}")

    # ------------------------------------------------------------------
    # Detection buffering helpers
    def _add_to_detection_buffer(self, detection: Detection, timestamp: float) -> None:
        """Add a successful detection to the buffer."""
        self._detection_buffer.append((detection, timestamp))
        self._last_detection_time = timestamp

    def _get_buffered_detection(self) -> Optional[Tuple[Detection, float]]:
        """Get the most recent buffered detection if it's within the timeout."""
        if not self._detection_buffer:
            return None
        
        detection, timestamp = self._detection_buffer[-1]
        time_since_detection = time.time() - timestamp
        
        if time_since_detection <= self._detection_timeout_s:
            return (detection, timestamp)
        
        return None

    def _get_last_frame(self) -> Optional[np.ndarray]:
        """Get the last frame from the detector if available."""
        # Try to get the last cached result from the detector
        if hasattr(self._detector, '_last_result') and self._detector._last_result:
            return self._detector._last_result.frame
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    def _run_loop(self, poll_interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                self.step()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("ObjectCenteringStrategy loop error: %s", exc)
            if poll_interval <= 0.0:
                continue
            self._stop_event.wait(poll_interval)

    def _compute_axis_errors(
        self,
        error_x: float,
        error_y: float,
        frame_width: int,
        frame_height: int,
    ) -> List[AxisError]:
        axis_errors: List[AxisError] = []
        horizontal = self._calibration.horizontal
        vertical = self._calibration.vertical
        current_time = time.time()
        if horizontal:
            effective_error = -error_x if self._invert_horizontal else error_x
            scaled_error = self._scale_error_for_resolution(
                effective_error,
                reference_dimension=self._calibration.reference_width,
                current_dimension=frame_width,
            )
            # PID control
            dt = current_time - self._pid_horizontal['prev_time']
            if dt > 0:
                p = self._pid_horizontal['kp'] * scaled_error
                self._pid_horizontal['integral'] += scaled_error * dt
                self._pid_horizontal['integral'] = max(-self._pid_horizontal['integral_max'], min(self._pid_horizontal['integral_max'], self._pid_horizontal['integral']))
                i = self._pid_horizontal['ki'] * self._pid_horizontal['integral']
                d = self._pid_horizontal['kd'] * (scaled_error - self._pid_horizontal['prev_error']) / dt
                velocity_scale = p + i + d
                self._pid_horizontal['prev_error'] = scaled_error
                self._pid_horizontal['prev_time'] = current_time
            else:
                velocity_scale = 0.0
            if horizontal.invert:
                velocity_scale *= -1
            distance_factor = abs(scaled_error) / (abs(scaled_error) + 100.0)
            velocity_scale *= distance_factor
            velocity_scale = max(-self._max_velocity, min(self._max_velocity, velocity_scale))
            axis_errors.append(AxisError(error_x, velocity_scale, horizontal.joint_indices))
            logger.debug(f"Horizontal: error_x={error_x:.1f}, scaled={scaled_error:.1f}, scale={velocity_scale:.3f}")
        if vertical:
            effective_error = -error_y if self._invert_vertical else error_y
            scaled_error = self._scale_error_for_resolution(
                effective_error,
                reference_dimension=self._calibration.reference_height,
                current_dimension=frame_height,
            )
            # PID control
            dt = current_time - self._pid_vertical['prev_time']
            if dt > 0:
                p = self._pid_vertical['kp'] * scaled_error
                self._pid_vertical['integral'] += scaled_error * dt
                self._pid_vertical['integral'] = max(-self._pid_vertical['integral_max'], min(self._pid_vertical['integral_max'], self._pid_vertical['integral']))
                i = self._pid_vertical['ki'] * self._pid_vertical['integral']
                d = self._pid_vertical['kd'] * (scaled_error - self._pid_vertical['prev_error']) / dt
                velocity_scale = p + i + d
                self._pid_vertical['prev_error'] = scaled_error
                self._pid_vertical['prev_time'] = current_time
            else:
                velocity_scale = 0.0
            if vertical.invert:
                velocity_scale *= -1
            distance_factor = abs(scaled_error) / (abs(scaled_error) + 50.0)
            velocity_scale *= distance_factor
            velocity_scale = max(-self._max_velocity, min(self._max_velocity, velocity_scale))
            axis_errors.append(AxisError(error_y, velocity_scale, vertical.joint_indices))
            logger.info(f"Vertical: error_y={error_y:.1f}, scaled={scaled_error:.1f}, scale={velocity_scale:.3f}")
        return axis_errors

    def _clear_active_target(self) -> None:
        self._active_target = None
        self._satisfied_since = None
        self._prev_error_timestamp = None
        self._prev_error_x = None
        self._prev_error_y = None
        self._filtered_error_x = None
        self._filtered_error_y = None
        self._swing_history_x.clear()
        self._swing_history_y.clear()
        self._current_swing_scale = 1.0
        self._last_total_scale = 1.0
        self._last_latency_scale = 1.0
        self._await_new_frame = False
        self._last_command_frame_ts = None
        self._next_command_time = 0.0
        # Reset PID
        self._pid_horizontal['integral'] = 0.0
        self._pid_horizontal['prev_error'] = 0.0
        self._pid_vertical['integral'] = 0.0
        self._pid_vertical['prev_error'] = 0.0

    @staticmethod
    def _scale_error_for_resolution(
        error_pixels: float,
        *,
        reference_dimension: Optional[int],
        current_dimension: int,
    ) -> float:
        scale = ObjectCenteringStrategy._resolution_scale(reference_dimension, current_dimension)
        return error_pixels * scale

    @staticmethod
    def _resolution_scale(reference_dimension: Optional[int], current_dimension: int) -> float:
        if not reference_dimension or reference_dimension <= 0:
            return 1.0
        if current_dimension <= 0:
            return 1.0
        return reference_dimension / float(current_dimension)

    @staticmethod
    def _pixel_error_to_delta(error_pixels: float, calibration: AxisCalibration) -> Optional[float]:
        if abs(error_pixels) <= calibration.deadband_pixels:
            return None
        if calibration.pixels_per_degree <= 1e-6:
            logger.debug("Invalid calibration: pixels_per_degree too small")
            return None
        delta_deg = (error_pixels / calibration.pixels_per_degree)
        if calibration.invert:
            delta_deg *= -1.0
        delta_deg *= calibration.gain
        if calibration.max_delta_deg > 0.0:
            delta_deg = max(-calibration.max_delta_deg, min(calibration.max_delta_deg, delta_deg))
        if abs(delta_deg) <= 1e-3:
            return None
        return delta_deg * _DEG_TO_RAD

    def _update_satisfaction_marker(
        self,
        _timestamp: Optional[float],
        error_x: Optional[float],
        error_y: Optional[float],
    ) -> bool:
        if self._satisfied_error_pixels <= 0.0 or self._satisfied_duration <= 0.0:
            self._satisfied_since = None
            return False
        if error_x is None or error_y is None:
            self._satisfied_since = None
            return False

        within = (
            abs(error_x) <= self._satisfied_error_pixels
            and abs(error_y) <= self._satisfied_error_pixels
        )
        if not within:
            self._satisfied_since = None
            return False

        now_ts = time.monotonic()
        if self._satisfied_since is None:
            self._satisfied_since = now_ts
            return False

        elapsed = now_ts - self._satisfied_since
        if elapsed >= self._satisfied_duration:
            return True
        return False

    def get_current_velocity_scales(self) -> Dict[int, float]:
        with self._lock:
            scales = {}
            for ae in self._last_axis_errors:
                for joint_index in ae.joint_indices:  # Iterate over all joints for this axis
                    scales[joint_index] = ae.velocity_scale * self._velocity_gain
            return scales

    def _dispatch_joint_targets(self, targets: Sequence[float], duration_s: Optional[float] = None) -> None:
        duration = duration_s if duration_s is not None else self._move_duration
        if self._use_motion_queue and self._motion_service is not None:
            command = JointCommand(list(targets), duration_s=duration)
            self._motion_service.enqueue(command)
        else:
            driver = self._resolve_driver()
            driver.send_joint_targets(list(targets), t_s=duration)

    def _maybe_display_frame(
        self,
        result: DetectionResult,
        target: Optional[Detection],
        error_x: Optional[float],
        error_y: Optional[float],
        axis_errors: Sequence[AxisError],
        predicted_errors: Optional[Tuple[float, float]] = None,
        command_errors: Optional[Tuple[float, float]] = None,
    ) -> None:
        if not self._display_feed or cv2 is None:
            return
        frame = result.frame
        if frame is None:
            return
        annotated = frame.copy()
        detections = list(result.detections)
        if detections:
            annotated = self._detector.apply_overlays(annotated, detections)
        if target is not None:
            x1, y1, x2, y2 = map(int, target.bbox.as_xyxy())
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
        height, width = annotated.shape[:2]
        center_point = (int(width / 2), int(height / 2))
        cv2.drawMarker(annotated, center_point, (255, 0, 0), cv2.MARKER_CROSS, 20, 2)

        overlay_lines: List[str] = []
        if error_x is not None and error_y is not None:
            overlay_lines.append(f"err_x: {error_x:.1f}px err_y: {error_y:.1f}px")
        if predicted_errors is not None:
            overlay_lines.append(
                f"pred_x: {predicted_errors[0]:.1f}px pred_y: {predicted_errors[1]:.1f}px"
            )
        if command_errors is not None:
            overlay_lines.append(
                f"cmd_x: {command_errors[0]:.1f}px cmd_y: {command_errors[1]:.1f}px"
            )
        overlay_lines.append(
            f"scale lat:{self._last_latency_scale:.2f} swing:{self._current_swing_scale:.2f} tot:{self._last_total_scale:.2f}"
        )
        for axis_error in axis_errors:
            joints_str = ", ".join(f"j{ji}" for ji in axis_error.joint_indices)
            deg = math.degrees(axis_error.velocity_scale * self._dt * self._max_velocity)
            overlay_lines.append(f"{joints_str}: {deg:.2f} deg")
        
        # Add gesture information
        with self._lock:
            gesture_status = "GESTURES:"
            if self._last_gesture_overlays:
                overlay_lines.append(gesture_status)
                overlay_lines.extend(self._last_gesture_overlays[:3])  # Limit to 3 gesture lines
            elif self._enable_gestures:
                overlay_lines.append("GESTURES: No hands detected")
            else:
                overlay_lines.append("GESTURES: Disabled")
                
            if self._paused:
                overlay_lines.append("STATUS: PAUSED (by gesture)")
            else:
                overlay_lines.append("STATUS: ACTIVE")
        
        if overlay_lines:
            y_offset = 20
            for line in overlay_lines[:4]:
                cv2.putText(
                    annotated,
                    line,
                    (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                y_offset += 18

        if not self._display_initialized:
            try:
                cv2.namedWindow(self._display_window_name, cv2.WINDOW_NORMAL)
            except Exception:
                logger.exception("Failed to create OpenCV window; disabling preview")
                self._display_feed = False
                return
            self._display_initialized = True

        # Draw hand landmarks and gesture predictions
        with self._lock:
            if self._last_hand_landmarks and self._last_handedness and mp is not None:
                try:
                    # Draw hand landmarks
                    for hand_landmarks, handedness in zip(self._last_hand_landmarks, self._last_handedness):
                        if hasattr(hand_landmarks, "landmark"):
                            mp.solutions.drawing_utils.draw_landmarks(
                                annotated, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS
                            )
                    
                    # Draw gesture predictions as text overlays on hands
                    y_offset = height - 100
                    for i, overlay in enumerate(self._last_gesture_overlays[:2]):  # Show top 2 predictions
                        cv2.putText(
                            annotated,
                            overlay,
                            (10, y_offset - i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (255, 255, 0),
                            2,
                            cv2.LINE_AA,
                        )
                except Exception as e:
                    logger.debug(f"Failed to draw hand landmarks: {e}")

        cv2.imshow(self._display_window_name, annotated)
        # Only process window events every 10 frames to reduce blocking
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 10 == 0:  # Process events every 10th frame
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                logger.info("Vision preview disabled by user input")
                self._display_feed = False
                self._close_display_window()
        else:
            # Check if window still exists without blocking
            if cv2.getWindowProperty(self._display_window_name, cv2.WND_PROP_VISIBLE) < 1:
                logger.info("Vision preview window closed by user")
                self._display_feed = False
                self._close_display_window()

    def _resolve_driver(self) -> ArmDriverProtocol:
        if not self._use_motion_queue and self._driver is not None:
            return self._driver
        if self._motion_service is not None and self._motion_service.driver is not None:
            return self._motion_service.driver  # type: ignore[return-value]
        if self._driver is not None:
            return self._driver
        raise RuntimeError("No driver available to send centering commands")

    def _record_status(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._last_status = dict(payload)

    def _close_display_window(self) -> None:
        if not self._display_initialized or cv2 is None:
            return
        try:
            cv2.destroyWindow(self._display_window_name)
        except Exception:
            logger.debug("Failed to destroy OpenCV window", exc_info=True)
        finally:
            self._display_initialized = False

    def is_satisfied(self) -> bool:
        if self._satisfied_since is None:
            return False
        return (time.monotonic() - self._satisfied_since) >= self._satisfied_duration

    def _anticipate_error(
        self,
        error_x: float,
        error_y: float,
        timestamp: float,
        lead_time: float,
    ) -> Tuple[float, float]:
        prev_ts = self._prev_error_timestamp
        prev_x = self._prev_error_x
        prev_y = self._prev_error_y

        predicted_x = error_x
        predicted_y = error_y
        if (
            prev_ts is not None
            and prev_x is not None
            and prev_y is not None
            and timestamp > prev_ts
        ):
            dt = max(1e-3, timestamp - prev_ts)
            rate_x = (error_x - prev_x) / dt
            rate_y = (error_y - prev_y) / dt
            horizon = max(0.0, min(lead_time, 0.6))
            projected_x = error_x + rate_x * horizon
            projected_y = error_y + rate_y * horizon
            if self._prediction_limit_px > 0.0:
                max_shift = self._prediction_limit_px
                shift_x = max(-max_shift, min(max_shift, projected_x - error_x))
                shift_y = max(-max_shift, min(max_shift, projected_y - error_y))
                predicted_x = error_x + shift_x
                predicted_y = error_y + shift_y
            else:
                predicted_x = projected_x
                predicted_y = projected_y

        self._prev_error_timestamp = timestamp
        self._prev_error_x = error_x
        self._prev_error_y = error_y
        return predicted_x, predicted_y

    def _apply_error_filter(self, value: float, previous: Optional[float]) -> float:
        alpha = self._error_filter_alpha
        if alpha <= 0.0 or previous is None:
            return value
        if alpha >= 1.0:
            return value
        return (alpha * value) + ((1.0 - alpha) * previous)

    def _update_swing_damping(self, error_x: float, error_y: float) -> float:
        if self._swing_damping_factor <= 0.0:
            return 1.0
        scale_x = self._swing_scale_for_axis(self._swing_history_x, error_x)
        scale_y = self._swing_scale_for_axis(self._swing_history_y, error_y)
        return min(scale_x, scale_y)

    def _swing_scale_for_axis(self, history: Deque[int], value: float) -> float:
        threshold = self._swing_tolerance_px
        sign = 0
        if value > threshold:
            sign = 1
        elif value < -threshold:
            sign = -1
        history.append(sign)
        non_zero = [s for s in history if s != 0]
        if len(non_zero) < 2:
            return 1.0
        changes = sum(1 for a, b in zip(non_zero, non_zero[1:]) if a != b)
        if changes == 0:
            return 1.0
        scale = 1.0 / (1.0 + changes * self._swing_damping_factor)
        return max(0.2, min(1.0, scale))

    def _compute_latency_scale(self, latency_seconds: float) -> float:
        if self._latency_slowdown <= 0.0:
            return 1.0
        scale = 1.0 / (1.0 + (max(0.0, latency_seconds) * self._latency_slowdown))
        return max(0.1, min(1.0, scale))

    def _process_gestures(self, frame: np.ndarray) -> None:
        """Process gestures from the frame and handle actions.

        Rate-limited to avoid blocking the control loop with MediaPipe inference.
        """
        if self._hands is None or self._gesture_recognizer is None:
            logger.debug("Gesture recognition not available (hands or recognizer not initialized)")
            return

        if not self._gesture_recognizer.enabled:
            logger.debug("Gesture recognizer not enabled (no classifier loaded)")
            return

        # Rate limit gesture processing to avoid blocking
        current_time = time.time()
        if current_time - self._last_gesture_process_time < self._gesture_process_interval:
            return
        self._last_gesture_process_time = current_time

        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if cv2 is not None else frame
        results = self._hands.process(rgb_frame)

        if not results.multi_hand_landmarks or not results.multi_handedness:
            logger.debug("No hands detected in frame")
            # Clear stored hand data
            with self._lock:
                self._last_hand_landmarks = None
                self._last_handedness = None
                self._last_gesture_overlays = []
            return

        hand_landmarks = results.multi_hand_landmarks
        handedness_list = results.multi_handedness
        handedness_labels = [h.classification[0].label for h in results.multi_handedness]
        logger.debug(f"Detected {len(hand_landmarks)} hands: {handedness_labels}")

        # Store hand data for display
        with self._lock:
            self._last_hand_landmarks = hand_landmarks
            self._last_handedness = handedness_labels

        events, overlays = self._gesture_recognizer.process(hand_landmarks, handedness_list)

        logger.debug(f"Gesture processing result: {len(events)} events, overlays: {overlays}")

        # Store overlays for display
        with self._lock:
            self._last_gesture_overlays = overlays

        if overlays:
            logger.info(f"Gesture predictions: {overlays}")

        for event in events:
            logger.info(f"Gesture event: {event.change} {event.event} (label: {event.label}, confidence: {event.confidence:.2f})")
            if event.change == "start":  # Only handle start events to avoid repeated actions
                if event.event == "teleop_pause":
                    self._paused = True
                    logger.info("Object centering paused by gesture (thumbs down)")
                elif event.event == "teleop_resume":
                    self._paused = False
                    logger.info("Object centering resumed by gesture (thumbs up)")
                elif event.event == "zero_all_joints":
                    self._dispatch_joint_targets([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], duration_s=2.0)
                    logger.info("Moving to zero pose by gesture (rock and roll)")


__all__ = ["ObjectCenteringStrategy", "TargetSelector", "ArmDriverProtocol"]
