"""
Base detector interface for vision-based detection.

This provides a common interface for different types of detectors (object, face, etc.)
that can be used with centering strategies.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple

import numpy as np


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box expressed in absolute pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    def center(self) -> Tuple[float, float]:
        """Return the center point of the bounding box."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def as_xyxy(self) -> Tuple[float, float, float, float]:
        """Return bounding box as (x1, y1, x2, y2)."""
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass(frozen=True)
class Detection:
    """A single detection result."""

    bbox: BoundingBox
    label: str
    confidence: float
    class_id: Optional[int] = None
    track_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bbox": self.bbox.as_xyxy(),
            "label": self.label,
            "confidence": self.confidence,
            "class_id": self.class_id,
            "track_id": self.track_id,
        }


@dataclass
class DetectionResult:
    """Result of a detection operation."""

    timestamp: float
    detections: Sequence[Detection]
    frame: Optional[np.ndarray] = None


class BaseDetector(ABC):
    """Abstract base class for detection systems."""

    def __init__(self):
        self._last_result: Optional[DetectionResult] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    @property
    def last_result(self) -> Optional[DetectionResult]:
        """Get the most recent detection result."""
        with self._lock:
            return self._last_result

    @abstractmethod
    def detect(
        self,
        *,
        frame: Optional[np.ndarray] = None,
        copy_frame: bool = False,
        return_frame: bool = True,
    ) -> Optional[DetectionResult]:
        """Perform detection on a frame or get cached result."""
        pass

    def start(self, *, poll_interval: float = 0.0) -> None:
        """Start background detection thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._loop,
            args=(poll_interval,),
        )
        self._worker_thread.start()

    def stop(self) -> None:
        """Stop background detection."""
        if self._worker_thread:
            self._stop_event.set()
            self._worker_thread.join(timeout=2.0)  # Add timeout to prevent hanging
            if self._worker_thread.is_alive():
                logger.warning("Detector thread did not stop within timeout")
            self._worker_thread = None

    def close(self) -> None:
        """Stop detection and release resources. Subclasses should override to release camera."""
        self.stop()

    def stream(
        self,
        *,
        poll_interval: float = 0.0,
        stop_event: Optional[threading.Event] = None,
    ) -> Generator[DetectionResult, None, None]:
        """Stream detection results."""
        while not (stop_event and stop_event.is_set()):
            result = self.detect()
            if result is not None:
                yield result
            if poll_interval > 0.0:
                import time
                time.sleep(poll_interval)

    @abstractmethod
    def _loop(self, poll_interval: float) -> None:
        """Background detection loop."""
        pass

    def apply_overlays(
        self,
        frame: np.ndarray,
        detections: Iterable[Detection],
        *,
        color: Tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
        font_scale: float = 0.5,
    ) -> np.ndarray:
        """Draw detection overlays on a frame."""
        import cv2
        for detection in detections:
            x1, y1, x2, y2 = map(int, detection.bbox.as_xyxy())
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            label = f"{detection.label}: {detection.confidence:.2f}"
            cv2.putText(
                frame,
                label,
                (x1, max(15, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                max(1, thickness // 2),
                cv2.LINE_AA,
            )
        return frame