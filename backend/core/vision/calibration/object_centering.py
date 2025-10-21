"""Utilities for storing and loading object-centering calibration data."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


@dataclass
class AxisCalibration:
    """Pixel-to-angle conversion parameters for a single camera axis."""

    joint_index: int
    pixels_per_degree: float
    invert: bool = False
    gain: float = 1.0
    deadband_pixels: float = 12.0
    max_delta_deg: float = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "joint_index": int(self.joint_index),
            "pixels_per_degree": float(self.pixels_per_degree),
            "invert": bool(self.invert),
            "gain": float(self.gain),
            "deadband_pixels": float(self.deadband_pixels),
            "max_delta_deg": float(self.max_delta_deg),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AxisCalibration":
        return cls(
            joint_index=int(payload.get("joint_index", 0)),
            pixels_per_degree=float(payload.get("pixels_per_degree", 1.0)),
            invert=bool(payload.get("invert", False)),
            gain=float(payload.get("gain", 1.0)),
            deadband_pixels=float(payload.get("deadband_pixels", 12.0)),
            max_delta_deg=float(payload.get("max_delta_deg", 4.0)),
        )


@dataclass
class ObjectCenteringCalibration:
    """Full calibration payload for object-centering control."""

    horizontal: Optional[AxisCalibration] = None
    vertical: Optional[AxisCalibration] = None
    reference_width: Optional[int] = None
    reference_height: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.horizontal is not None:
            payload["horizontal"] = self.horizontal.to_dict()
        if self.vertical is not None:
            payload["vertical"] = self.vertical.to_dict()
        if self.reference_width is not None:
            payload["reference_width"] = int(self.reference_width)
        if self.reference_height is not None:
            payload["reference_height"] = int(self.reference_height)
        payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ObjectCenteringCalibration":
        horizontal = payload.get("horizontal")
        vertical = payload.get("vertical")
        metadata = payload.get("metadata") or {}
        return cls(
            horizontal=AxisCalibration.from_dict(horizontal) if isinstance(horizontal, dict) else None,
            vertical=AxisCalibration.from_dict(vertical) if isinstance(vertical, dict) else None,
            reference_width=(int(payload["reference_width"]) if "reference_width" in payload else None),
            reference_height=(int(payload["reference_height"]) if "reference_height" in payload else None),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def ensure_complete(self) -> None:
        if self.horizontal is None or self.vertical is None:
            raise ValueError("Calibration must define both horizontal and vertical axes")
        if self.reference_width is None or self.reference_height is None:
            raise ValueError("Calibration must include reference_width and reference_height")

    def touch_metadata(self, *, axis: Optional[str] = None) -> None:
        stamp = _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.metadata["updated_at"] = stamp
        if axis:
            self.metadata[f"last_updated_{axis}"] = stamp


DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parent / "object_centering.yml"


def load_calibration(path: Optional[Path | str] = None) -> ObjectCenteringCalibration:
    candidate = Path(path) if path is not None else DEFAULT_CALIBRATION_PATH
    if not candidate.is_absolute():
        candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Calibration file not found: {candidate}")
    with candidate.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return ObjectCenteringCalibration.from_dict(payload)


def save_calibration(
    calibration: ObjectCenteringCalibration,
    path: Optional[Path | str] = None,
) -> Path:
    candidate = Path(path) if path is not None else DEFAULT_CALIBRATION_PATH
    if not candidate.is_absolute():
        candidate = candidate.resolve()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    calibration.touch_metadata()
    with candidate.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(calibration.to_dict(), handle, sort_keys=False)
    return candidate


def update_axis(
    calibration: ObjectCenteringCalibration,
    axis: str,
    axis_calibration: AxisCalibration,
    *,
    frame_size: Optional[Tuple[int, int]] = None,
) -> ObjectCenteringCalibration:
    axis_lower = axis.lower()
    if axis_lower not in {"horizontal", "vertical"}:
        raise ValueError("axis must be either 'horizontal' or 'vertical'")
    if axis_lower == "horizontal":
        calibration.horizontal = axis_calibration
    else:
        calibration.vertical = axis_calibration
    if frame_size is not None:
        width, height = frame_size
        calibration.reference_width = int(width)
        calibration.reference_height = int(height)
    calibration.touch_metadata(axis=axis_lower)
    return calibration


__all__ = [
    "AxisCalibration",
    "ObjectCenteringCalibration",
    "DEFAULT_CALIBRATION_PATH",
    "load_calibration",
    "save_calibration",
    "update_axis",
]
