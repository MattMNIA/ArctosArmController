from abc import ABC, abstractmethod
from typing import Tuple, Any


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
