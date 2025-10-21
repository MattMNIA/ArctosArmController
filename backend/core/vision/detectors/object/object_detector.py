"""
Object detection utilities that integrate the camera manager with Ultralytics YOLO.

The detector wraps the camera abstraction used by the rest of the vision module so
that strategies can request frames and structured detections without having to know
anything about the specific camera implementation or the YOLO inference details.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

from ...camera_manager import CameraManager
from ...cameras import CameraBase

try:  # Ultralytics provides the YOLO (YOLOv8/YOLOv9/YoloE) implementation we target.
	import ultralytics  # type: ignore[import]
except ImportError as exc:  # pragma: no cover - handled gracefully at runtime.
	ultralytics = None  # type: ignore[assignment]
	_YOLO_IMPORT_ERROR: Optional[BaseException] = exc
else:  # pragma: no cover - the attribute is only used when import succeeds.
	_YOLO_IMPORT_ERROR = None

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
		return (self.x1 + self.width * 0.5, self.y1 + self.height * 0.5)

	def as_xyxy(self) -> Tuple[float, float, float, float]:
		return (self.x1, self.y1, self.x2, self.y2)

	def as_xywh(self) -> Tuple[float, float, float, float]:
		return (self.x1, self.y1, self.width, self.height)


@dataclass(frozen=True)
class ObjectDetection:
	"""Single detection returned by YOLO with metadata useful for strategies."""

	label: str
	confidence: float
	bbox: BoundingBox
	class_id: Optional[int] = None
	tracker_id: Optional[int] = None

	def to_dict(self) -> Dict[str, Any]:
		return {
			"label": self.label,
			"confidence": float(self.confidence),
			"bbox": self.bbox.as_xyxy(),
			"bbox_xywh": self.bbox.as_xywh(),
			"center": self.bbox.center(),
			"classId": self.class_id,
			"trackerId": self.tracker_id,
		}


@dataclass
class DetectionResult:
	"""Detection payload containing the frame timestamp and all detections."""

	timestamp: float
	detections: List[ObjectDetection]
	frame: Optional[np.ndarray] = None

	def to_strategy_payload(self) -> Dict[str, Any]:
		return {
			"timestamp": self.timestamp,
			"detections": [detection.to_dict() for detection in self.detections],
		}


class ObjectDetector:
	"""High-level helper that couples a camera with a YOLO (YoloE) model."""

	def __init__(
		self,
		camera_manager: CameraManager,
		*,
		model: Union[str, Path, None] = None,
		device: Optional[str] = None,
		confidence_threshold: float = 0.25,
		iou_threshold: float = 0.45,
		classes: Optional[Sequence[int]] = None,
		imgsz: Optional[Union[int, Tuple[int, int]]] = None,
		max_frame_size: Optional[Tuple[int, int]] = None,
		frame_retry_attempts: int = 3,
		autoload: bool = True,
	) -> None:
		self._camera_manager = camera_manager
		self._camera: Optional[CameraBase] = None
		self._model_source = str(model) if model is not None else "yolov8n.pt"
		self._device = device
		self._confidence = float(confidence_threshold)
		self._iou = float(iou_threshold)
		self._classes = tuple(classes) if classes is not None else None
		self._imgsz = imgsz
		self._max_frame_size = max_frame_size
		self._frame_retry_attempts = max(1, int(frame_retry_attempts))
		self._model: Optional[Any] = None
		self._last_result: Optional[DetectionResult] = None
		self._lock = threading.Lock()
		self._stop_event = threading.Event()
		self._worker_thread: Optional[threading.Thread] = None

		if autoload:
			self._model = self._load_model(self._model_source)

	@property
	def model(self) -> Any:
		return self._ensure_model_loaded()

	@property
	def last_result(self) -> Optional[DetectionResult]:
		with self._lock:
			return self._last_result

	def start(self, *, poll_interval: float = 0.0) -> None:
		if self._worker_thread and self._worker_thread.is_alive():
			return
		self._stop_event.clear()
		self._worker_thread = threading.Thread(
			target=self._loop,
			args=(poll_interval,),
			daemon=True,
			name="object-detector",
		)
		self._worker_thread.start()

	def stop(self) -> None:
		self._stop_event.set()
		if self._worker_thread:
			self._worker_thread.join(timeout=1.0)
		self._worker_thread = None

	def close(self) -> None:
		self.stop()
		with self._lock:
			self._camera = None

	def detect(
		self,
		*,
		frame: Optional[np.ndarray] = None,
		copy_frame: bool = False,
		return_frame: bool = True,
	) -> Optional[DetectionResult]:
		model = self._ensure_model_loaded()
		grabbed_frame = frame if frame is not None else self._grab_frame()
		if grabbed_frame is None:
			logger.debug("ObjectDetector.detect: no frame available from camera")
			return None

		processed_frame = self._resize_if_needed(grabbed_frame)
		inference_frame = processed_frame.copy() if copy_frame else processed_frame

		detections = self._run_inference(model, inference_frame)
		result = DetectionResult(
			timestamp=time.time(),
			detections=detections,
			frame=inference_frame if return_frame else None,
		)
		with self._lock:
			self._last_result = result
		return result

	def stream(
		self,
		*,
		poll_interval: float = 0.0,
		stop_event: Optional[threading.Event] = None,
	) -> Generator[DetectionResult, None, None]:
		while not (stop_event and stop_event.is_set()):
			result = self.detect()
			if result is not None:
				yield result
			if poll_interval > 0.0:
				time.sleep(poll_interval)

	def apply_overlays(
		self,
		frame: np.ndarray,
		detections: Iterable[ObjectDetection],
		*,
		color: Tuple[int, int, int] = (0, 255, 0),
		thickness: int = 2,
		font_scale: float = 0.5,
	) -> np.ndarray:
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

	def _loop(self, poll_interval: float) -> None:
		while not self._stop_event.is_set():
			try:
				self.detect()
			except Exception as exc:  # pragma: no cover - defensive logging.
				logger.exception("ObjectDetector background loop failed: {exc}")
			if poll_interval > 0.0:
				self._stop_event.wait(poll_interval)

	def _ensure_model_loaded(self) -> Any:
		if self._model is None:
			self._model = self._load_model(self._model_source)
		return self._model

	def _load_model(self, model_reference: Union[str, Path]) -> Any:
		if ultralytics is None:
			message = (
				"ultralytics is not installed – install it or add it to requirements "
				"to enable object detection"
			)
			raise ImportError(message) from _YOLO_IMPORT_ERROR
		logger.info("Loading YOLO model from %s", model_reference)
		yolo_ctor = getattr(ultralytics, "YOLO", None)
		if yolo_ctor is None:
			raise RuntimeError("The installed ultralytics package does not expose a YOLO constructor")
		return yolo_ctor(model_reference)

	def _grab_frame(self) -> Optional[np.ndarray]:
		camera = self._get_camera()
		for _ in range(self._frame_retry_attempts):
			ret, frame = camera.read()
			if ret and isinstance(frame, np.ndarray):
				return frame
		logger.warning("ObjectDetector: failed to read frame after %s attempts", self._frame_retry_attempts)
		return None

	def _get_camera(self) -> CameraBase:
		if self._camera is None or not self._camera.is_opened():
			self._camera = self._camera_manager.get_camera()
		return self._camera

	def _resize_if_needed(self, frame: np.ndarray) -> np.ndarray:
		if self._max_frame_size is None:
			return frame
		width, height = self._max_frame_size
		if width <= 0 or height <= 0:
			return frame
		return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)

	def _run_inference(self, model: Any, frame: np.ndarray) -> List[ObjectDetection]:
		predict_kwargs: Dict[str, Any] = {
			"conf": self._confidence,
			"iou": self._iou,
			"device": self._device,
			"classes": list(self._classes) if self._classes is not None else None,
			"verbose": False,
		}
		if self._imgsz is not None:
			predict_kwargs["imgsz"] = self._imgsz

		results = model.predict(frame, **predict_kwargs)
		if not results:
			return []

		result = results[0]
		boxes = getattr(result, "boxes", None)
		if boxes is None or boxes.xyxy is None or len(boxes) == 0:
			return []

		names: Dict[int, str]
		if isinstance(result.names, dict):
			names = {int(idx): str(label) for idx, label in result.names.items()}
		else:
			names = {idx: str(label) for idx, label in enumerate(getattr(result, "names", []) or [])}

		xyxy = boxes.xyxy
		conf = boxes.conf
		cls = boxes.cls
		ids = getattr(boxes, "id", None)

		xyxy_np = xyxy.cpu().numpy() if hasattr(xyxy, "cpu") else np.asarray(xyxy)
		conf_np = conf.cpu().numpy() if hasattr(conf, "cpu") else np.asarray(conf)
		cls_np = cls.cpu().numpy() if hasattr(cls, "cpu") else np.asarray(cls)
		if ids is not None:
			if hasattr(ids, "cpu"):
				id_np = ids.cpu().numpy()
			else:
				id_np = np.asarray(ids)
		else:
			id_np = None

		detections: List[ObjectDetection] = []
		for idx, coords in enumerate(xyxy_np):
			x1, y1, x2, y2 = coords.tolist()
			confidence = float(conf_np[idx]) if idx < len(conf_np) else 0.0
			class_id: Optional[int]
			if idx < len(cls_np):
				try:
					class_id = int(cls_np[idx])
				except (TypeError, ValueError):
					class_id = None
			else:
				class_id = None
			tracker_id: Optional[int]
			if id_np is not None and idx < len(id_np):
				value = id_np[idx]
				tracker_id = int(value) if value is not None else None
			else:
				tracker_id = None
			if class_id is not None and class_id in names:
				label = names[class_id]
			else:
				label = str(class_id) if class_id is not None else "unknown"
			detections.append(
				ObjectDetection(
					label=label,
					confidence=confidence,
					bbox=BoundingBox(
						x1=float(x1),
						y1=float(y1),
						x2=float(x2),
						y2=float(y2),
					),
					class_id=class_id,
					tracker_id=tracker_id,
				)
			)
		return detections


__all__ = [
	"BoundingBox",
	"ObjectDetection",
	"DetectionResult",
	"ObjectDetector",
]

