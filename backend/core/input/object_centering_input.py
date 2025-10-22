from __future__ import annotations

import logging
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .base_input import InputController
from ..vision.camera_manager import CameraManager
from ..vision.detectors.object.object_detector import ObjectDetector
from ..vision.strategy.object_centering_strategy import ObjectCenteringStrategy
from ..motion_service import MotionService


logger = logging.getLogger(__name__)

# Optional MediaPipe import for gesture recognition
try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    mp = None
    MP_AVAILABLE = False


class ObjectCenteringInput(InputController):
    """Input adapter that runs the object-centering strategy as a teleop source."""

    DEFAULT_CAMERA_CONFIG = Path(__file__).resolve().parents[2] / "config" / "default.yml"

    def __init__(
        self,
        *,
        motion_service: Optional[MotionService] = None,
        driver=None,
        camera_config: Optional[Union[str, Path]] = None,
        detector_type: str = "object",  # "object" or "face"
        detector_model: Optional[Union[str, Path]] = None,
        preferred_labels: Optional[Sequence[str]] = None,
        calibration_path: Optional[Union[str, Path]] = None,
        min_confidence: float = 0.7,
        command_interval: float = 0.3,
        move_duration: float = 0.4,
        use_motion_queue: bool = True,
        detector_kwargs: Optional[Dict[str, Any]] = None,
        display_feed: bool = False,
        display_window_name: Optional[str] = None,
        invert_horizontal: bool = False,
        invert_vertical: bool = False,
        enable_gestures: bool = False,
        gesture_config_path: Optional[Union[str, Path]] = None,
        gesture_update_interval: float = 0.1,
    ) -> None:
        if motion_service is None and driver is None:
            raise ValueError("ObjectCenteringInput requires either a motion_service or driver instance")
        if use_motion_queue and motion_service is None:
            raise ValueError("use_motion_queue=True requires a motion_service instance")

        config_path = Path(camera_config) if camera_config is not None else self.DEFAULT_CAMERA_CONFIG
        if not config_path.is_absolute():
            config_path = config_path.resolve()

        self._camera_manager = CameraManager(config_path)

        if detector_type == "face":
            from ..vision.detectors.face.face_detector import FaceDetector
            self._detector = FaceDetector(self._camera_manager, **(detector_kwargs or {}))
        elif detector_type == "object":
            detector_args = dict(detector_kwargs or {})
            if detector_model is not None:
                detector_args.setdefault("model", str(detector_model))
            detector_args.setdefault("confidence_threshold", float(min_confidence))
            detector_args.setdefault("imgsz", 256)
            detector_args.setdefault("max_frame_size", (640, 480))
            detector_args.setdefault("device", "cpu")  # Force CPU usage to avoid CUDA issues
            self._detector = ObjectDetector(self._camera_manager, **detector_args)
        else:
            raise ValueError(f"Unsupported detector_type: {detector_type}")
        self._strategy = ObjectCenteringStrategy(
            self._detector,
            motion_service=motion_service,
            driver=driver,
            calibration_path=calibration_path,
            preferred_labels=preferred_labels,
            min_confidence=min_confidence,
            command_interval=command_interval,
            move_duration=move_duration,
            use_motion_queue=use_motion_queue,
            display_feed=display_feed,
            display_window_name=display_window_name,
            invert_horizontal=invert_horizontal,
            invert_vertical=invert_vertical,
        )
        self._strategy.start(poll_interval=0.05)
        self._previous_scales: Dict[int, float] = {}

        # Initialize gesture recognition
        self._gesture_recognizer = None
        self._pending_gesture_events: List[Tuple[str, Union[int, str], float]] = []
        self._gesture_update_interval = max(0.0, gesture_update_interval)
        self._last_gesture_update = 0.0
        
        # Initialize MediaPipe for gesture processing
        self._mp_hands = None
        self._mp_drawing = None
        self._lock = threading.Lock()
        
        if enable_gestures:
            if not MP_AVAILABLE or mp is None:
                logger.warning("MediaPipe not available - gesture recognition disabled")
            else:
                try:
                    self._mp_hands = mp.solutions.hands.Hands(
                        max_num_hands=2,
                        min_detection_confidence=0.7,
                        min_tracking_confidence=0.6,
                    )
                    self._mp_drawing = mp.solutions.drawing_utils
                    
                    from ..vision.detectors.gesture.gesture_recognizer import GestureRecognizer
                    self._gesture_recognizer = GestureRecognizer(gesture_config_path, model="mlp")
                    if not self._gesture_recognizer.enabled:
                        logger.warning("Gesture recognizer not enabled - model may not be available")
                        self._gesture_recognizer = None
                except ImportError as e:
                    logger.warning(f"Could not import gesture recognizer: {e}")
                    self._gesture_recognizer = None
                except Exception as e:
                    logger.warning(f"Failed to initialize gesture recognition: {e}")
                    self._gesture_recognizer = None

    def get_commands(self) -> Dict[Union[int, str], float]:
        return {}

    def get_events(self) -> List[Tuple[str, Any, float]]:
        current_scales = self._strategy.get_current_velocity_scales()
        logger.debug(f"ObjectCenteringInput current_scales: {current_scales}")

        events = []
        for joint, scale in current_scales.items():
            prev = self._previous_scales.get(joint, 0)
            if abs(scale) > 0.005 and abs(prev) <= 0.005:
                events.append(('press', joint, scale))
            elif abs(scale) <= 0.005 and abs(prev) > 0.005:
                events.append(('release', joint, 0))
            elif abs(scale - prev) > 0.005:
                events.append(('press', joint, scale))

        for joint in set(self._previous_scales) - set(current_scales):
            if abs(self._previous_scales[joint]) > 0.005:
                events.append(('release', joint, 0))

        self._previous_scales = current_scales.copy()
        
        # Process gestures if enabled
        if self._gesture_recognizer is not None and self._mp_hands is not None:
            gesture_events = self._process_gestures()
            events.extend(gesture_events)
        
        logger.debug(f"ObjectCenteringInput events: {events}")
        return events

    def _process_gestures(self) -> List[Tuple[str, Union[int, str], float]]:
        """Process camera frames for gesture recognition."""
        if self._gesture_recognizer is None or self._mp_hands is None:
            return []
            
        with self._lock:
            # Check if MediaPipe solution is still valid (not closed)
            if self._mp_hands is None or not hasattr(self._mp_hands, 'process'):
                logger.debug("ObjectCenteringInput._process_gestures: MediaPipe solution is closed")
                return []
                
            # Get the latest frame from the detector instead of reading directly from camera
            last_result = self._detector.last_result
            if last_result is None:
                logger.debug("ObjectCenteringInput._process_gestures: no detection result available yet")
                return []
                
            if last_result.frame is None:
                logger.debug("ObjectCenteringInput._process_gestures: detection result has no frame")
                return []
                
            frame = last_result.frame
            if frame is None or not hasattr(frame, 'shape') or len(frame.shape) != 3:
                logger.debug("ObjectCenteringInput._process_gestures: invalid frame")
                return []
                
            # Process frame with MediaPipe
            frame_rgb = frame.copy()
            import cv2
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            try:
                results = self._mp_hands.process(frame_rgb)
            except Exception as e:
                logger.warning(f"ObjectCenteringInput._process_gestures: MediaPipe process failed: {e}")
                return []
            
            # Update gesture recognizer
            now = time.time()
            if (
                self._gesture_update_interval > 0.0
                and now - self._last_gesture_update >= self._gesture_update_interval
            ):
                multi_hand_landmarks = results.multi_hand_landmarks if results else None
                multi_handedness = results.multi_handedness if results else None
                
                gesture_events, _ = self._gesture_recognizer.process(multi_hand_landmarks, multi_handedness)
                
                # Convert gesture events to teleop events
                for event in gesture_events:
                    if event.change == "start":
                        self._pending_gesture_events.append(
                            ("press", event.event, max(event.confidence, 0.0))
                        )
                    elif event.change == "end":
                        self._pending_gesture_events.append(("release", event.event, 0.0))
                
                self._last_gesture_update = now
            
            # Return pending gesture events
            if not self._pending_gesture_events:
                return []
                
            events = list(self._pending_gesture_events)
            self._pending_gesture_events = []
            return events

    def _consume_gesture_events(self) -> List[Tuple[str, Union[int, str], float]]:
        """Consume any pending gesture events."""
        with self._lock:
            if not self._pending_gesture_events:
                return []
            events = list(self._pending_gesture_events)
            self._pending_gesture_events = []
            return events

    def set_target_label(self, label: Optional[str]) -> None:
        self._strategy.set_target_label(label)

    def set_target_labels(self, labels: Optional[Sequence[str]]) -> None:
        self._strategy.set_target_labels(labels)

    def get_status(self) -> Dict[str, Any]:
        return self._strategy.get_status()

    def close(self) -> None:
        """Clean up resources."""
        self._strategy.stop()
        if self._mp_hands is not None:
            self._mp_hands.close()
            self._mp_hands = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


