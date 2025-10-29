import logging
import threading
import time
from typing import Any, Dict, List, Optional, cast

from .teleop_controller import TeleopController, DriverProtocol
from .motion_service import MotionService
from .input.base_input import InputController
from .input.keyboard_input import KeyboardController
from .input.xbox_input import XboxController
from .input.finger_input import FingerInput as FingerInputController
from .input.finger_slider_input import FingerSliderInput
from .input.object_centering_input import ObjectCenteringInput

logger = logging.getLogger(__name__)


class TeleopManagerError(RuntimeError):
    """Raised when the teleoperation manager cannot complete a request."""


class TeleopManager:
    """Central coordinator for runtime-configurable teleoperation modes."""

    _AVAILABLE_MODES: Dict[str, Dict[str, Any]] = {
        "keyboard": {
            "label": "Keyboard",
            "description": "Map WASD-style keyboard input to joint velocity control.",
            "supportsOptions": False,
        },
        "xbox": {
            "label": "Xbox Controller",
            "description": "Use an Xbox gamepad for analog joint velocity control.",
            "supportsOptions": False,
        },
        "fingers": {
            "label": "Finger Tracking",
            "description": "Experimental finger-gesture controller.",
            "supportsOptions": False,
        },
        "finger-sliders": {
            "label": "Finger Sliders",
            "description": "Finger-tracking input with virtual sliders.",
            "supportsOptions": False,
        },
        "object-centering": {
            "label": "Object Centering",
            "description": "Autonomously center the preferred detection label in view.",
            "supportsOptions": True,
            "options": {
                "centerLabel": {
                    "type": "string",
                    "label": "Preferred label",
                    "placeholder": "person",
                },
                "detectorModel": {
                    "type": "string",
                    "label": "Detector model",
                    "placeholder": "yolov8n.pt",
                },
                "detectorType": {
                    "type": "string",
                    "label": "Detector type",
                    "default": "object",
                    "options": ["object", "face"],
                },
                "gestureConfigPath": {
                    "type": "string",
                    "label": "Gesture config path",
                    "placeholder": "backend/core/vision/detectors/gesture/gestures.yml",
                },
                "displayFeed": {
                    "type": "boolean",
                    "label": "Show annotated feed",
                    "default": False,
                },
                "invertHorizontal": {
                    "type": "boolean",
                    "label": "Invert horizontal",
                    "default": False,
                },
                "invertVertical": {
                    "type": "boolean",
                    "label": "Invert vertical",
                    "default": False,
                },
            },
        },
    }

    def __init__(self, motion_service: MotionService) -> None:
        self._motion_service = motion_service
        driver = getattr(motion_service, "driver", None)
        if driver is None:
            raise TeleopManagerError("Motion service does not have an attached driver")
        self._driver = cast(DriverProtocol, driver)
        self._lock = threading.Lock()
        self._teleop_controller: Optional[TeleopController] = None
        self._input_controller: Optional[InputController] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._current_mode: Optional[str] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    def available_modes(self) -> List[Dict[str, Any]]:
        return [
            {"id": key, **value}
            for key, value in self._AVAILABLE_MODES.items()
        ]

    def current_state(self) -> Dict[str, Any]:
        with self._lock:
            controller = self._teleop_controller
            mode = self._current_mode
            running = controller is not None and self._thread is not None and self._thread.is_alive()
            last_error = self._last_error
        return {
            "mode": mode,
            "running": running,
            "lastError": last_error,
        }

    def start_mode(self, mode: str, *, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode not in self._AVAILABLE_MODES:
            raise TeleopManagerError(f"Unknown teleoperation mode '{mode}'")

        if not self._motion_service.running:
            raise TeleopManagerError("Motion service is not running")

        input_controller = self._create_input_controller(normalized_mode, options)
        teleop_controller = TeleopController(input_controller, self._driver, self._motion_service)

        # For object-centering mode, start unpaused since it's autonomous
        if normalized_mode == "object-centering":
            teleop_controller._paused = False

        with self._lock:
            self._stop_locked()
            self._teleop_controller = teleop_controller
            self._input_controller = input_controller
            self._current_mode = normalized_mode
            self._last_error = None
            self._stop_event.clear()
            loop_interval = 1.0 / getattr(teleop_controller, "teleop_hz", 50.0)
            self._thread = threading.Thread(
                target=self._loop,
                name=f"teleop-{normalized_mode}",
                args=(loop_interval,),
                daemon=True,
            )
            self._thread.start()

        logger.info("Teleoperation mode '%s' activated", normalized_mode)
        return self.current_state()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self._current_mode = None
            self._last_error = None
        logger.info("Teleoperation stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    def _loop(self, interval: float) -> None:
        while not self._stop_event.is_set():
            controller: Optional[TeleopController]
            with self._lock:
                controller = self._teleop_controller
            if controller is None:
                break
            try:
                controller.teleop_step()
            except Exception as exc:  # pragma: no cover - runtime protection
                logger.exception("Teleoperation loop error: %s", exc)
                with self._lock:
                    self._last_error = str(exc)
                time.sleep(interval)
            else:
                time.sleep(interval)

    def _stop_locked(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        controller = self._teleop_controller
        input_controller = self._input_controller
        self._teleop_controller = None
        self._input_controller = None
        self._stop_event.clear()

        if controller is not None:
            try:
                controller.stop_all()
            except Exception:  # pragma: no cover - best effort
                logger.debug("Error while stopping teleop controller", exc_info=True)

        if input_controller is not None:
            close_method = getattr(input_controller, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:  # pragma: no cover - best effort cleanup
                    logger.debug("Error while closing input controller", exc_info=True)

    def _create_input_controller(self, mode: str, options: Dict[str, Any]) -> InputController:
        if mode == "keyboard":
            return KeyboardController()
        if mode == "xbox":
            return XboxController()
        if mode == "fingers":
            return FingerInputController()
        if mode == "finger-sliders":
            return FingerSliderInput(gesture_update_interval=0.1)
        if mode == "object-centering":
            preferred_label = options.get("centerLabel")
            labels = [preferred_label] if preferred_label else None
            display_feed = bool(options.get("displayFeed", False))
            detector_model = options.get("model") or options.get("detectorModel")
            detector_type = options.get("detectorType", "object")
            invert_horizontal = bool(options.get("invertHorizontal", False))
            invert_vertical = bool(options.get("invertVertical", False))
            gesture_config_path = options.get("gestureConfigPath")
            return ObjectCenteringInput(
                motion_service=self._motion_service,
                driver=self._driver,
                preferred_labels=labels,
                detector_type=detector_type,
                detector_model=detector_model,
                use_motion_queue=True,
                display_feed=display_feed,
                invert_horizontal=invert_horizontal,
                invert_vertical=invert_vertical,
                gesture_config_path=gesture_config_path,
            )
        raise TeleopManagerError(f"Unsupported teleoperation mode '{mode}'")


__all__ = ["TeleopManager", "TeleopManagerError"]
