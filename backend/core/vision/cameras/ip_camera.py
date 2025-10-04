import cv2
from .camera_base import CameraBase


class IPCamera(CameraBase):
    """Handles IP camera capture using OpenCV."""

    def __init__(self, url: str):
        self._url = url
        self._capture = cv2.VideoCapture(url)
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(f"Failed to open IP camera at {url}.")

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
    def url(self):
        """Get the camera URL."""
        return self._url
