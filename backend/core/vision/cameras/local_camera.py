from __future__ import annotations

from typing import Any, Dict, Optional

import cv2

from .camera_base import CameraBase
from .camera_controls import LOCAL_CAMERA_CONTROLS, CameraControlDefinition, ControlType
from .camera_selector import select_camera_index


class LocalCamera(CameraBase):
    """Handles local camera capture using OpenCV."""

    _PROPERTY_MAP: Dict[str, int] = {
        "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast": cv2.CAP_PROP_CONTRAST,
        "saturation": cv2.CAP_PROP_SATURATION,
        "gain": cv2.CAP_PROP_GAIN,
        "exposure": cv2.CAP_PROP_EXPOSURE,
    }

    _OPTIONAL_PROPERTY_MAP: Dict[str, str] = {
        "sharpness": "CAP_PROP_SHARPNESS",
        "auto_wb": "CAP_PROP_AUTO_WB",
    }

    def __init__(self, camera_index: Optional[int] = None):
        selected_index = select_camera_index(camera_index)
        self._camera_index = selected_index
        self._capture = cv2.VideoCapture(selected_index, cv2.CAP_DSHOW)
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(f"Failed to open camera index {selected_index}.")

        self._control_definitions = self._build_control_definitions()

    def _build_control_definitions(self) -> Dict[str, CameraControlDefinition]:
        definitions: Dict[str, CameraControlDefinition] = {}
        for control_id, property_id in self._PROPERTY_MAP.items():
            if property_id is not None:
                definitions[control_id] = LOCAL_CAMERA_CONTROLS[control_id]

        for control_id, attr_name in self._OPTIONAL_PROPERTY_MAP.items():
            property_id = getattr(cv2, attr_name, None)
            if property_id is not None:
                self._PROPERTY_MAP[control_id] = property_id
                definitions[control_id] = LOCAL_CAMERA_CONTROLS[control_id]

        return definitions

    # ------------------------------------------------------------------
    # Video capture primitives
    def read(self):
        """Read a frame from the camera."""
        return self._capture.read()

    def release(self):
        """Release the camera capture."""
        if self._capture and self._capture.isOpened():
            self._capture.release()

    def is_opened(self):
        """Check if the camera is opened."""
        return self._capture.isOpened()

    @property
    def camera_index(self):
        """Get the selected camera index."""
        return self._camera_index

    # ------------------------------------------------------------------
    # Configuration helpers
    def get_supported_controls(self) -> Dict[str, CameraControlDefinition]:
        return self._control_definitions

    def get_control_value(self, control_id: str) -> Any:
        definition = self._control_definitions.get(control_id)
        if not definition:
            raise KeyError(f"Control '{control_id}' is not supported by {self.__class__.__name__}")

        property_id = self._PROPERTY_MAP.get(control_id)
        if property_id is None:
            raise KeyError(f"No property mapping for control '{control_id}'")

        value = self._capture.get(property_id)
        if value == -1:
            return definition.default

        if definition.control_type is ControlType.TOGGLE:
            return bool(round(value))
        return int(round(value))

    def set_control_value(self, control_id: str, value: Any) -> None:
        definition = self._control_definitions.get(control_id)
        if not definition:
            raise KeyError(f"Control '{control_id}' is not supported by {self.__class__.__name__}")

        property_id = self._PROPERTY_MAP.get(control_id)
        if property_id is None:
            raise KeyError(f"No property mapping for control '{control_id}'")

        normalized_value = self._normalize_value(definition, value)
        success = self._capture.set(property_id, normalized_value)
        if not success:
            raise RuntimeError(f"Failed to set control '{control_id}' on camera index {self._camera_index}")

    def _normalize_value(self, definition: CameraControlDefinition, value: Any) -> float:
        if definition.control_type is ControlType.TOGGLE:
            return 1.0 if bool(value) else 0.0

        if isinstance(value, str) and value.startswith("0x"):
            value = int(value, 16)

        numeric = float(value)
        if definition.min_value is not None:
            numeric = max(definition.min_value, numeric)
        if definition.max_value is not None:
            numeric = min(definition.max_value, numeric)
        return numeric
