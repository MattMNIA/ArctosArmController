from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
import requests

from .camera_base import CameraBase
from .camera_controls import IP_CAMERA_CONTROLS, CameraControlDefinition, ControlType

logger = logging.getLogger(__name__)


class IPCamera(CameraBase):
    """Handles IP camera capture and configuration via the ESP32 camera API.

    Uses a background thread to continuously grab frames, ensuring the latest
    frame is always available without blocking and reducing latency.
    """

    def __init__(
        self,
        url: str,
        control_base_url: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._session = requests.Session()
        self._control_base_url = self._derive_control_base_url(control_base_url)
        self._capture = cv2.VideoCapture(url)
        if not self._capture or not self._capture.isOpened():
            self._session.close()
            raise RuntimeError(f"Failed to open IP camera at {url}.")

        # Set buffer size to minimum to reduce latency
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Background frame grabbing for reduced latency
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_available = False
        self._stop_event = threading.Event()
        self._grab_thread = threading.Thread(
            target=self._grab_frames_loop,
            daemon=True,
            name="ip-camera-grab"
        )
        self._grab_thread.start()

    def _derive_control_base_url(self, control_base_url: Optional[str]) -> str:
        if control_base_url:
            return control_base_url.rstrip("/")

        parsed = urlparse(self._url)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(
                "Unable to determine control base URL; please provide control_base_url explicitly."
            )
        return f"{parsed.scheme}://{parsed.hostname}"

    # ------------------------------------------------------------------
    # Background frame grabbing
    def _grab_frames_loop(self) -> None:
        """Continuously grab frames in background to keep buffer fresh."""
        while not self._stop_event.is_set():
            if not self._capture or not self._capture.isOpened():
                break
            try:
                ret, frame = self._capture.read()
                if ret and frame is not None:
                    with self._frame_lock:
                        self._latest_frame = frame
                        self._frame_available = True
                else:
                    # Brief sleep on failure to avoid spinning
                    time.sleep(0.01)
            except Exception as e:
                logger.debug("Frame grab error: %s", e)
                time.sleep(0.01)

    # ------------------------------------------------------------------
    # Video capture primitives
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Read the latest frame from the camera (non-blocking).

        Returns the most recent frame captured by the background thread,
        ensuring minimal latency.
        """
        with self._frame_lock:
            if self._frame_available and self._latest_frame is not None:
                # Return a copy to avoid race conditions
                frame = self._latest_frame.copy()
                return True, frame
            return False, None

    def release(self) -> None:
        """Release the camera capture and HTTP session."""
        # Signal the grab thread to stop
        self._stop_event.set()

        # Wait briefly for thread to finish (don't block forever)
        if self._grab_thread and self._grab_thread.is_alive():
            self._grab_thread.join(timeout=0.5)

        if self._capture and self._capture.isOpened():
            self._capture.release()
        if self._session:
            self._session.close()

    def is_opened(self) -> bool:
        """Check if the camera is opened."""
        return self._capture is not None and self._capture.isOpened()

    def take_picture(self) -> bytes:
        """Trigger the camera to capture a still image and return JPEG bytes."""

        params = {"_cb": int(time.time() * 1000)}
        try:
            response = self._session.get(
                f"{self._control_base_url}/capture",
                params=params,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to capture still image: %s", exc)
            raise RuntimeError("Failed to capture still image from IP camera") from exc

        if not response.content:
            raise RuntimeError("Received empty response when capturing still image")

        return response.content

    @property
    def url(self) -> str:
        """Get the camera stream URL."""

        return self._url

    @property
    def control_base_url(self) -> str:
        """Base URL used to hit the ESP32 configuration endpoints."""

        return self._control_base_url

    # ------------------------------------------------------------------
    # Configuration helpers
    def get_supported_controls(self) -> Dict[str, CameraControlDefinition]:
        return IP_CAMERA_CONTROLS

    def get_all_control_values(self) -> Dict[str, Any]:
        status = self._fetch_status()
        controls = self.get_supported_controls()
        return {
            control_id: self._coerce_value(definition, status.get(control_id))
            for control_id, definition in controls.items()
        }

    def get_control_value(self, control_id: str) -> Any:
        controls = self.get_supported_controls()
        if control_id not in controls:
            raise KeyError(f"Control '{control_id}' is not supported by {self.__class__.__name__}")

        status = self._fetch_status()
        return self._coerce_value(controls[control_id], status.get(control_id))

    def set_control_value(self, control_id: str, value: Any) -> None:
        controls = self.get_supported_controls()
        if control_id not in controls:
            raise KeyError(f"Control '{control_id}' is not supported by {self.__class__.__name__}")

        normalized_value = self._normalize_value(controls[control_id], value)
        try:
            response = self._session.get(
                f"{self._control_base_url}/control",
                params={"var": control_id, "val": normalized_value},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to set control '%s': %s", control_id, exc)
            raise RuntimeError(f"Failed to set control '{control_id}'") from exc

    def set_register(self, register: int, mask: int, value: int, offset: int = 0) -> None:
        adjusted_value = (value & mask) << offset
        adjusted_mask = mask << offset
        try:
            response = self._session.get(
                f"{self._control_base_url}/reg",
                params={"reg": register, "mask": adjusted_mask, "val": adjusted_value},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to set register 0x%x: %s", register, exc)
            raise RuntimeError(f"Failed to write register 0x{register:x}") from exc

    def get_register(self, register: int, mask: int, offset: int = 0) -> int:
        adjusted_mask = mask << offset
        try:
            response = self._session.get(
                f"{self._control_base_url}/greg",
                params={"reg": register, "mask": adjusted_mask},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to read register 0x%x: %s", register, exc)
            raise RuntimeError(f"Failed to read register 0x{register:x}") from exc

        raw_value = int(response.text.strip())
        return (raw_value & adjusted_mask) >> offset

    def set_xclk(self, frequency_mhz: int) -> None:
        try:
            response = self._session.get(
                f"{self._control_base_url}/xclk",
                params={"xclk": frequency_mhz},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to set XCLK frequency: %s", exc)
            raise RuntimeError("Failed to set XCLK frequency") from exc

    def set_pll(
        self,
        bypass: int,
        mul: int,
        sys: int,
        root: int,
        pre: int,
        seld5: int,
        pclken: int,
        pclk: int,
    ) -> None:
        try:
            response = self._session.get(
                f"{self._control_base_url}/pll",
                params={
                    "bypass": bypass,
                    "mul": mul,
                    "sys": sys,
                    "root": root,
                    "pre": pre,
                    "seld5": seld5,
                    "pclken": pclken,
                    "pclk": pclk,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to configure PLL: %s", exc)
            raise RuntimeError("Failed to configure PLL") from exc

    def set_window(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        offset_x: int,
        offset_y: int,
        total_x: int,
        total_y: int,
        output_x: int,
        output_y: int,
        scaling: int,
        binning: int,
    ) -> None:
        try:
            response = self._session.get(
                f"{self._control_base_url}/resolution",
                params={
                    "sx": start_x,
                    "sy": start_y,
                    "ex": end_x,
                    "ey": end_y,
                    "offx": offset_x,
                    "offy": offset_y,
                    "tx": total_x,
                    "ty": total_y,
                    "ox": output_x,
                    "oy": output_y,
                    "scale": scaling,
                    "binning": binning,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to configure window: %s", exc)
            raise RuntimeError("Failed to configure window") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    def _fetch_status(self) -> Dict[str, Any]:
        try:
            response = self._session.get(
                f"{self._control_base_url}/status", timeout=self._timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch camera status: %s", exc)
            raise RuntimeError("Failed to fetch camera status") from exc

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Camera status response was not JSON: %s", exc)
            raise RuntimeError("Malformed status response from camera") from exc

    @staticmethod
    def _coerce_value(definition: CameraControlDefinition, raw_value: Any) -> Any:
        if raw_value is None:
            return definition.default

        if definition.control_type is ControlType.TOGGLE:
            if isinstance(raw_value, str):
                return bool(int(raw_value))
            return bool(raw_value)

        try:
            if isinstance(raw_value, str):
                raw_value = float(raw_value)
            return int(raw_value)
        except (TypeError, ValueError):
            return raw_value

    @staticmethod
    def _normalize_value(definition: CameraControlDefinition, value: Any) -> Any:
        if definition.control_type is ControlType.TOGGLE:
            return 1 if bool(value) else 0

        if definition.control_type is ControlType.SELECT:
            # Selection values are integer enumerations on the ESP32 camera
            if isinstance(value, str) and value.startswith("0x"):
                return int(value, 16)
            return int(value)

        # Range controls: coerce to integer before sending
        if isinstance(value, str) and value.startswith("0x"):
            return int(value, 16)
        return int(float(value))
