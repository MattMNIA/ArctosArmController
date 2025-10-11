from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple


class ControlType(str, Enum):
    """Enumeration of camera control widget types."""

    RANGE = "range"
    TOGGLE = "toggle"
    SELECT = "select"


@dataclass(frozen=True)
class CameraControlOption:
    """Selectable option for list-based camera controls."""

    value: Any
    label: str

    def as_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class CameraControlDefinition:
    """Metadata for a single camera control."""

    id: str
    label: str
    control_type: ControlType
    description: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    options: Tuple[CameraControlOption, ...] = ()
    default: Optional[Any] = None

    def to_dict(self, value: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "type": self.control_type.value,
            "value": value,
        }
        if self.description:
            payload["description"] = self.description
        if self.min_value is not None:
            payload["min"] = self.min_value
        if self.max_value is not None:
            payload["max"] = self.max_value
        if self.step is not None:
            payload["step"] = self.step
        if self.options:
            payload["options"] = [option.as_dict() for option in self.options]
        if self.default is not None:
            payload["default"] = self.default
        return payload


# --- IP camera controls ----------------------------------------------------

_FRAMESIZE_OPTIONS: Tuple[CameraControlOption, ...] = (
    CameraControlOption(21, "QSXGA (2560x1920)"),
    CameraControlOption(20, "Portrait FHD (1080x1920)"),
    CameraControlOption(19, "WQXGA (2560x1600)"),
    CameraControlOption(18, "QHD (2560x1440)"),
    CameraControlOption(17, "QXGA (2048x1564)"),
    CameraControlOption(16, "Portrait 3MP (864x1564)"),
    CameraControlOption(15, "Portrait HD (720x1280)"),
    CameraControlOption(14, "FHD (1920x1080)"),
    CameraControlOption(13, "UXGA (1600x1200)"),
    CameraControlOption(12, "SXGA (1280x1024)"),
    CameraControlOption(11, "HD (1280x720)"),
    CameraControlOption(10, "XGA (1024x768)"),
    CameraControlOption(9, "SVGA (800x600)"),
    CameraControlOption(8, "VGA (640x480)"),
    CameraControlOption(7, "HVGA (480x320)"),
    CameraControlOption(6, "CIF (400x296)"),
    CameraControlOption(5, "QVGA (320x240)"),
    CameraControlOption(4, "240x240"),
    CameraControlOption(3, "HQVGA (240x176)"),
    CameraControlOption(2, "QCIF (176x144)"),
    CameraControlOption(1, "QQVGA (160x120)"),
    CameraControlOption(0, "96x96"),
)

_SPECIAL_EFFECT_OPTIONS: Tuple[CameraControlOption, ...] = (
    CameraControlOption(0, "No Effect"),
    CameraControlOption(1, "Negative"),
    CameraControlOption(2, "Grayscale"),
    CameraControlOption(3, "Red Tint"),
    CameraControlOption(4, "Green Tint"),
    CameraControlOption(5, "Blue Tint"),
    CameraControlOption(6, "Sepia"),
)

_WB_MODE_OPTIONS: Tuple[CameraControlOption, ...] = (
    CameraControlOption(0, "Auto"),
    CameraControlOption(1, "Sunny"),
    CameraControlOption(2, "Cloudy"),
    CameraControlOption(3, "Office"),
    CameraControlOption(4, "Home"),
)

IP_CAMERA_CONTROLS: Dict[str, CameraControlDefinition] = {
    "framesize": CameraControlDefinition(
        id="framesize",
        label="Resolution",
        control_type=ControlType.SELECT,
        options=_FRAMESIZE_OPTIONS,
        description="Output resolution for the IP camera stream.",
    ),
    "quality": CameraControlDefinition(
        id="quality",
        label="JPEG Quality",
        control_type=ControlType.RANGE,
        min_value=4,
        max_value=63,
        step=1,
        description="JPEG compression quality (lower is better quality).",
    ),
    "brightness": CameraControlDefinition(
        id="brightness",
        label="Brightness",
        control_type=ControlType.RANGE,
        min_value=-3,
        max_value=3,
        step=1,
    ),
    "contrast": CameraControlDefinition(
        id="contrast",
        label="Contrast",
        control_type=ControlType.RANGE,
        min_value=-3,
        max_value=3,
        step=1,
    ),
    "saturation": CameraControlDefinition(
        id="saturation",
        label="Saturation",
        control_type=ControlType.RANGE,
        min_value=-4,
        max_value=4,
        step=1,
    ),
    "sharpness": CameraControlDefinition(
        id="sharpness",
        label="Sharpness",
        control_type=ControlType.RANGE,
        min_value=-3,
        max_value=3,
        step=1,
    ),
    "denoise": CameraControlDefinition(
        id="denoise",
        label="De-Noise",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=8,
        step=1,
    ),
    "ae_level": CameraControlDefinition(
        id="ae_level",
        label="Exposure Level",
        control_type=ControlType.RANGE,
        min_value=-5,
        max_value=5,
        step=1,
    ),
    "gainceiling": CameraControlDefinition(
        id="gainceiling",
        label="Gain Ceiling",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=511,
        step=1,
    ),
    "special_effect": CameraControlDefinition(
        id="special_effect",
        label="Special Effect",
        control_type=ControlType.SELECT,
        options=_SPECIAL_EFFECT_OPTIONS,
    ),
    "awb": CameraControlDefinition(
        id="awb",
        label="Auto White Balance",
        control_type=ControlType.TOGGLE,
    ),
    "dcw": CameraControlDefinition(
        id="dcw",
        label="Advanced AWB",
        control_type=ControlType.TOGGLE,
    ),
    "awb_gain": CameraControlDefinition(
        id="awb_gain",
        label="Manual AWB",
        control_type=ControlType.TOGGLE,
    ),
    "wb_mode": CameraControlDefinition(
        id="wb_mode",
        label="AWB Mode",
        control_type=ControlType.SELECT,
        options=_WB_MODE_OPTIONS,
    ),
    "aec": CameraControlDefinition(
        id="aec",
        label="Auto Exposure",
        control_type=ControlType.TOGGLE,
    ),
    "aec_value": CameraControlDefinition(
        id="aec_value",
        label="Manual Exposure",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=1920,
        step=1,
    ),
    "aec2": CameraControlDefinition(
        id="aec2",
        label="Night Mode",
        control_type=ControlType.TOGGLE,
    ),
    "agc": CameraControlDefinition(
        id="agc",
        label="Auto Gain",
        control_type=ControlType.TOGGLE,
    ),
    "agc_gain": CameraControlDefinition(
        id="agc_gain",
        label="Manual Gain",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=64,
        step=1,
    ),
    "raw_gma": CameraControlDefinition(
        id="raw_gma",
        label="GMA Enable",
        control_type=ControlType.TOGGLE,
    ),
    "lenc": CameraControlDefinition(
        id="lenc",
        label="Lens Correction",
        control_type=ControlType.TOGGLE,
    ),
    "hmirror": CameraControlDefinition(
        id="hmirror",
        label="Horizontal Mirror",
        control_type=ControlType.TOGGLE,
    ),
    "vflip": CameraControlDefinition(
        id="vflip",
        label="Vertical Flip",
        control_type=ControlType.TOGGLE,
    ),
    "bpc": CameraControlDefinition(
        id="bpc",
        label="Bad Pixel Correction",
        control_type=ControlType.TOGGLE,
    ),
    "wpc": CameraControlDefinition(
        id="wpc",
        label="White Pixel Correction",
        control_type=ControlType.TOGGLE,
    ),
    "colorbar": CameraControlDefinition(
        id="colorbar",
        label="Color Bar",
        control_type=ControlType.TOGGLE,
    ),
    "face_detect": CameraControlDefinition(
        id="face_detect",
        label="Face Detection",
        control_type=ControlType.TOGGLE,
    ),
    "face_recognize": CameraControlDefinition(
        id="face_recognize",
        label="Face Recognition",
        control_type=ControlType.TOGGLE,
    ),
}


# --- Local camera controls -------------------------------------------------

LOCAL_CAMERA_CONTROLS: Dict[str, CameraControlDefinition] = {
    "brightness": CameraControlDefinition(
        id="brightness",
        label="Brightness",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=255,
        step=1,
    ),
    "contrast": CameraControlDefinition(
        id="contrast",
        label="Contrast",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=255,
        step=1,
    ),
    "saturation": CameraControlDefinition(
        id="saturation",
        label="Saturation",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=255,
        step=1,
    ),
    "sharpness": CameraControlDefinition(
        id="sharpness",
        label="Sharpness",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=255,
        step=1,
    ),
    "gain": CameraControlDefinition(
        id="gain",
        label="Analog Gain",
        control_type=ControlType.RANGE,
        min_value=0,
        max_value=255,
        step=1,
    ),
    "exposure": CameraControlDefinition(
        id="exposure",
        label="Exposure",
        control_type=ControlType.RANGE,
        min_value=-13,
        max_value=-1,
        step=1,
    ),
    "auto_wb": CameraControlDefinition(
        id="auto_wb",
        label="Auto White Balance",
        control_type=ControlType.TOGGLE,
    ),
}


def get_controls(camera_type: str) -> Dict[str, CameraControlDefinition]:
    """Return control definitions for the specified camera type."""

    camera_type = camera_type.lower()
    if camera_type == "ip":
        return IP_CAMERA_CONTROLS
    if camera_type == "local":
        return LOCAL_CAMERA_CONTROLS
    return {}


__all__ = [
    "ControlType",
    "CameraControlOption",
    "CameraControlDefinition",
    "IP_CAMERA_CONTROLS",
    "LOCAL_CAMERA_CONTROLS",
    "get_controls",
]
