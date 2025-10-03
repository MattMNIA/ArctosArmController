from typing import Any, Dict, Tuple
import cv2

class FrameAdapter:
    """Utility class for adapting frames between different formats and resolutions."""

    @staticmethod
    def resize_frame(frame: Any, width: int, height: int) -> Any:
        """Resize the given frame to the specified width and height."""
        return cv2.resize(frame, (width, height))

    @staticmethod
    def convert_color(frame: Any, color_space: int) -> Any:
        """Convert the color space of the given frame."""
        return cv2.cvtColor(frame, color_space)

    @staticmethod
    def get_frame_dimensions(frame: Any) -> Tuple[int, int]:
        """Get the dimensions of the given frame."""
        return frame.shape[1], frame.shape[0]  # width, height

    @staticmethod
    def normalize_frame(frame: Any) -> Any:
        """Normalize the frame values to the range [0, 1]."""
        return frame / 255.0 if frame is not None else None

    @staticmethod
    def adapt_frame(frame: Any, width: int, height: int, color_space: int) -> Any:
        """Resize and convert the color space of the frame."""
        resized_frame = FrameAdapter.resize_frame(frame, width, height)
        return FrameAdapter.convert_color(resized_frame, color_space)