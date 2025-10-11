from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from .camera_controls import CameraControlDefinition


class CameraBase(ABC):
    """Abstract base class for camera implementations."""

    @abstractmethod
    def read(self) -> Tuple[bool, Any]:
        """Read a frame from the camera."""
        pass

    @abstractmethod
    def release(self) -> None:
        """Release the camera resources."""
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """Check if the camera is opened."""
        pass

    # --- Optional configuration API -------------------------------------

    def get_supported_controls(self) -> Dict[str, CameraControlDefinition]:
        """Return metadata for controls supported by this camera."""

        return {}

    def get_control_value(self, control_id: str) -> Any:
        """Return the current value for the specified control."""

        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_control_value"
        )

    def set_control_value(self, control_id: str, value: Any) -> None:
        """Set the value for the specified control."""

        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement set_control_value"
        )

    def get_all_control_values(self) -> Dict[str, Any]:
        """Return current values for all supported controls."""

        controls = self.get_supported_controls()
        return {control_id: self.get_control_value(control_id) for control_id in controls}
