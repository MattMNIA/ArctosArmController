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
            "type": "primary",
        },
        "xbox": {
            "label": "Xbox Controller",
            "description": "Use an Xbox gamepad for analog joint velocity control.",
            "supportsOptions": False,
            "type": "primary",
        },
        "fingers": {
            "label": "Finger Tracking",
            "description": "Experimental finger-gesture controller.",
            "supportsOptions": False,
            "type": "primary",
        },
        "finger-sliders": {
            "label": "Finger Sliders",
            "description": "Finger-tracking input with virtual sliders.",
            "supportsOptions": False,
            "type": "primary",
        },
        "object-centering": {
            "label": "Object Centering",
            "description": "Autonomously center the preferred detection label in view.",
            "supportsOptions": True,
            "type": "primary",
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
                "enableGestures": {
                    "type": "boolean",
                    "label": "Enable gesture recognition",
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
        
        # Primary control mode
        self._primary_controller: Optional[TeleopController] = None
        self._primary_input: Optional[InputController] = None
        self._primary_mode: Optional[str] = None
        
        # Gesture overlay
        self._gesture_controller: Optional[TeleopController] = None
        self._gesture_input: Optional[InputController] = None
        self._gesture_mode: Optional[str] = None
        self._gesture_enabled: bool = False
        
        # Control state
        self._paused: bool = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
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
            primary_mode = self._primary_mode
            running = (self._primary_controller is not None or self._gesture_controller is not None) and self._thread is not None and self._thread.is_alive()
            paused = self._paused
            last_error = self._last_error
        return {
            "primaryMode": primary_mode,
            "running": running,
            "paused": paused,
            "lastError": last_error,
        }

    def start_mode(self, mode: str, *, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start a primary control mode."""
        options = options or {}
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode not in self._AVAILABLE_MODES:
            raise TeleopManagerError(f"Unknown teleoperation mode '{mode}'")

        mode_info = self._AVAILABLE_MODES[normalized_mode]
        if mode_info.get("type") != "primary":
            raise TeleopManagerError(f"Mode '{mode}' is not a primary control mode")

        if not self._motion_service.running:
            raise TeleopManagerError("Motion service is not running")

        input_controller = self._create_input_controller(normalized_mode, options)
        teleop_controller = TeleopController(input_controller, self._driver, self._motion_service)

        with self._lock:
            # Stop existing control thread and controller
            self._stop_locked()
            
            # Stop existing primary controller
            if self._primary_controller is not None:
                try:
                    self._primary_controller.stop_all()
                except Exception:
                    logger.debug("Error stopping previous primary controller", exc_info=True)
                if self._primary_input is not None:
                    close_method = getattr(self._primary_input, "close", None)
                    if callable(close_method):
                        try:
                            close_method()
                        except Exception:
                            logger.debug("Error closing previous primary input", exc_info=True)

            self._primary_controller = teleop_controller
            self._primary_input = input_controller
            self._primary_mode = normalized_mode
            self._paused = False  # Start unpaused

            # Start new control thread
            self._start_control_thread_locked()

        logger.info("Primary teleoperation mode '%s' activated", normalized_mode)
        return self.current_state()


    def pause(self) -> Dict[str, Any]:
        """Pause the current primary mode (if pausable)."""
        with self._lock:
            if self._primary_mode == "object-centering" and self._primary_controller is not None:
                self._primary_controller._pause_teleop()
                self._paused = True
            else:
                raise TeleopManagerError("Current mode does not support pausing")

        logger.info("Primary mode paused")
        return self.current_state()

    def resume(self) -> Dict[str, Any]:
        """Resume the paused primary mode."""
        with self._lock:
            if self._primary_mode == "object-centering" and self._paused and self._primary_controller is not None:
                self._primary_controller._resume_teleop()
                self._paused = False
            else:
                raise TeleopManagerError("No paused mode to resume")

        logger.info("Primary mode resumed")
        return self.current_state()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self._primary_mode = None
            self._gesture_mode = None
            self._gesture_enabled = False
            self._paused = False
            self._last_error = None
        logger.info("Teleoperation stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    def _start_control_thread_locked(self) -> None:
        """Start the control thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return  # Already running

        self._stop_event.clear()
        loop_interval = 1.0 / 50.0  # 50 Hz control loop
        self._thread = threading.Thread(
            target=self._loop,
            name="teleop-control",
            args=(loop_interval,),
            daemon=True,
        )
        self._thread.start()

    def _loop(self, interval: float) -> None:
        while not self._stop_event.is_set():
            primary_controller = None
            gesture_controller = None
            
            with self._lock:
                primary_controller = self._primary_controller
                gesture_controller = self._gesture_controller if self._gesture_enabled else None

            # Handle primary controller
            if primary_controller is not None:
                try:
                    primary_controller.teleop_step()
                except Exception as exc:
                    logger.exception("Primary controller step failed: %s", exc)
                    with self._lock:
                        self._last_error = str(exc)

            # Handle gesture controller (always active when enabled)
            if gesture_controller is not None:
                try:
                    gesture_controller.teleop_step()
                except Exception as exc:
                    logger.exception("Gesture controller step failed: %s", exc)
                    with self._lock:
                        self._last_error = str(exc)

            if interval > 0.0:
                self._stop_event.wait(interval)

    def _stop_locked(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        
        # Stop primary controller
        if self._primary_controller is not None:
            try:
                self._primary_controller.stop_all()
            except Exception:
                logger.debug("Error stopping primary controller", exc_info=True)
        if self._primary_input is not None:
            close_method = getattr(self._primary_input, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    logger.debug("Error closing primary input", exc_info=True)
        
        # Stop gesture controller
        if self._gesture_controller is not None:
            try:
                self._gesture_controller.stop_all()
            except Exception:
                logger.debug("Error stopping gesture controller", exc_info=True)
        if self._gesture_input is not None:
            close_method = getattr(self._gesture_input, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception:
                    logger.debug("Error closing gesture input", exc_info=True)

        self._primary_controller = None
        self._primary_input = None
        self._gesture_controller = None
        self._gesture_input = None
        self._stop_event.clear()

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
            enable_gestures = bool(options.get("enableGestures", False))
            
            # Configure detector arguments
            detector_args = {}
            if detector_model is not None:
                detector_args["model"] = detector_model
            detector_args["confidence_threshold"] = 0.7
            detector_args["imgsz"] = 640  # Use standard size instead of 256
            detector_args["max_frame_size"] = (640, 480)
            
            # Force CPU if CUDA not available
            try:
                import torch
                if not torch.cuda.is_available():
                    detector_args["device"] = "cpu"
            except ImportError:
                detector_args["device"] = "cpu"
            
            return ObjectCenteringInput(
                motion_service=self._motion_service,
                driver=self._driver,
                preferred_labels=labels,
                detector_type=detector_type,
                detector_kwargs=detector_args,
                use_motion_queue=True,
                display_feed=display_feed,
                invert_horizontal=invert_horizontal,
                invert_vertical=invert_vertical,
                enable_gestures=enable_gestures,
            )
        raise TeleopManagerError(f"Unsupported teleoperation mode '{mode}'")


__all__ = ["TeleopManager", "TeleopManagerError"]
