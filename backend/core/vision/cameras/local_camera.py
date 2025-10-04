import cv2
from typing import Optional
from .camera_base import CameraBase
from .camera_selector import select_camera_index


class LocalCamera(CameraBase):
    """Handles local camera capture using OpenCV."""

    def __init__(self, camera_index: Optional[int] = None):
        selected_index = select_camera_index(camera_index)
        self._camera_index = selected_index
        self._capture = cv2.VideoCapture(selected_index, cv2.CAP_DSHOW)
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(f"Failed to open camera index {selected_index}.")

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
