from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .base_input import InputController
from ..vision.camera_manager import CameraManager
from ..vision.detectors.object.object_detector import ObjectDetector
from ..vision.strategy.object_centering_strategy import ObjectCenteringStrategy
from ..motion_service import MotionService


logger = logging.getLogger(__name__)


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
            detector_args.setdefault("imgsz", 416)  # Increased from 256 for better accuracy
            detector_args.setdefault("max_frame_size", (854, 480))  # HD aspect ratio
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
        logger.debug(f"ObjectCenteringInput events: {events}")

        return events

    def set_target_label(self, label: Optional[str]) -> None:
        self._strategy.set_target_label(label)

    def set_target_labels(self, labels: Optional[Sequence[str]]) -> None:
        self._strategy.set_target_labels(labels)

    def get_status(self) -> Dict[str, Any]:
        return self._strategy.get_status()

    def close(self) -> None:
        self._strategy.stop()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


