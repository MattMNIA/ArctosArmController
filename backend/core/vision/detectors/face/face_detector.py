"""
Face detection using OpenCV Haar cascades.

This detector finds faces in images using pre-trained Haar cascade classifiers.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from ...camera_manager import CameraManager
from ...cameras import CameraBase
from ..base_detector import BaseDetector, BoundingBox, Detection, DetectionResult

logger = logging.getLogger(__name__)


class FaceDetector(BaseDetector):
    """Face detector using OpenCV Haar cascades."""

    CASCADE_URL = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"

    def __init__(
        self,
        camera_manager: CameraManager,
        *,
        cascade_path: Optional[str] = None,
        scale_factor: float = 1.1,
        min_neighbors: int = 10,  # Reduced from 12 to improve detection reliability
        min_size: tuple[int, int] = (50, 50),  # Increased from (30, 30) to filter small detections
        max_size: Optional[tuple[int, int]] = None,
    ) -> None:
        super().__init__()
        self._camera_manager = camera_manager
        self._camera: Optional[CameraBase] = None
        self._scale_factor = scale_factor
        self._min_neighbors = min_neighbors
        self._min_size = min_size
        self._max_size = max_size

        # Load Haar cascade
        if cascade_path is None:
            cascade_path = self._get_or_download_cascade()
        else:
            cascade_path = str(Path(cascade_path).resolve())

        self._face_cascade = cv2.CascadeClassifier(str(cascade_path))
        if self._face_cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade from {cascade_path}")

    @staticmethod
    def _get_or_download_cascade() -> str:
        """Get the path to the Haar cascade file, downloading it if necessary."""
        # Try OpenCV installation first
        try:
            opencv_path = Path(cv2.__file__).parent / "data" / "haarcascades" / "haarcascade_frontalface_default.xml"
            if opencv_path.exists():
                return str(opencv_path)
        except:
            pass

        # Try local data directory
        local_data_dir = Path(__file__).parent.parent.parent.parent / "data"
        local_data_dir.mkdir(exist_ok=True)
        cascade_path = local_data_dir / "haarcascade_frontalface_default.xml"

        if cascade_path.exists():
            return str(cascade_path)

        # Download the cascade file
        logger.info(f"Downloading Haar cascade from {FaceDetector.CASCADE_URL}")
        try:
            urllib.request.urlretrieve(FaceDetector.CASCADE_URL, cascade_path)
            logger.info(f"Downloaded cascade to {cascade_path}")
            return str(cascade_path)
        except Exception as e:
            raise RuntimeError(f"Could not find or download Haar cascade file: {e}")

    def detect(
        self,
        *,
        frame: Optional[np.ndarray] = None,
        copy_frame: bool = False,
        return_frame: bool = True,
    ) -> Optional[DetectionResult]:
        # If providing a specific frame, process it synchronously
        if frame is not None:
            return self._detect_frame(frame, copy_frame, return_frame)
        
        # If background detection is running, return the latest cached result
        if self._worker_thread and self._worker_thread.is_alive():
            with self._lock:
                return self._last_result
        
        # Otherwise, perform synchronous detection
        return self._detect_frame(None, copy_frame, return_frame)

    def _grab_frame(self) -> Optional[np.ndarray]:
        camera = self._get_camera()
        for _ in range(3):  # retry attempts
            ret, frame = camera.read()
            if ret and isinstance(frame, np.ndarray):
                return frame
        logger.warning("FaceDetector: failed to read frame after retries")
        return None

    def _get_camera(self):
        if self._camera is None or not self._camera.is_opened():
            self._camera = self._camera_manager.get_camera()
        return self._camera

    def _detect_faces(self, frame: np.ndarray) -> List[Detection]:
        # Convert to grayscale for Haar cascade
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect faces
        kwargs = {
            "scaleFactor": self._scale_factor,
            "minNeighbors": self._min_neighbors,
            "minSize": self._min_size,
        }
        if self._max_size is not None:
            kwargs["maxSize"] = self._max_size
        faces = self._face_cascade.detectMultiScale(gray, **kwargs)

        detections = []
        for (x, y, w, h) in faces:
            # Filter out detections that are too small or have bad aspect ratios
            aspect_ratio = w / h
            if aspect_ratio < 0.5 or aspect_ratio > 2.0:  # Faces should be roughly square
                continue
            if w < 60 or h < 60:  # Minimum size filter
                continue
                
            bbox = BoundingBox(
                x1=float(x),
                y1=float(y),
                x2=float(x + w),
                y2=float(y + h),
            )
            detection = Detection(
                bbox=bbox,
                label="face",
                confidence=1.0,  # Haar cascade doesn't provide confidence
                class_id=0,
            )
            detections.append(detection)

        return detections

    def _detect_frame(
        self,
        frame: Optional[np.ndarray],
        copy_frame: bool,
        return_frame: bool,
    ) -> Optional[DetectionResult]:
        grabbed_frame = frame if frame is not None else self._grab_frame()
        if grabbed_frame is None:
            logger.debug("FaceDetector._detect_frame: no frame available")
            return None

        inference_frame = grabbed_frame.copy() if copy_frame else grabbed_frame
        detections = self._detect_faces(inference_frame)

        result = DetectionResult(
            timestamp=0.0,  # Will be set by caller
            detections=detections,
            frame=inference_frame if return_frame else None,
        )
        with self._lock:
            self._last_result = result
        return result

    def _loop(self, poll_interval: float) -> None:
        import time
        while not self._stop_event.is_set():
            try:
                result = self._detect_frame(None, copy_frame=False, return_frame=True)
                if result is not None:
                    result.timestamp = time.time()  # Set timestamp here
                    with self._lock:
                        self._last_result = result
            except Exception as exc:
                logger.exception("FaceDetector background loop failed: %s", exc)
            if poll_interval > 0.0:
                self._stop_event.wait(poll_interval)