from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

from utils.config_manager import ConfigManager

from .cameras import CameraBase, IPCamera, LocalCamera


class CameraManager:
    """Lazily instantiate and manage access to the configured camera."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._lock = threading.Lock()
        self._camera: Optional[CameraBase] = None
        self._config_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    def get_camera(self) -> CameraBase:
        with self._lock:
            if self._camera is None or not self._camera.is_opened():
                self._camera = self._create_camera()
            return self._camera

    def get_camera_type(self) -> str:
        config = self._get_config()
        return (config.get("type") or "ip").lower()

    def describe_camera(self) -> Dict[str, Any]:
        config = self._get_config()
        camera_type = (config.get("type") or "ip").lower()
        info: Dict[str, Any] = {"type": camera_type}

        if camera_type == "ip":
            ip_cfg = config.get("ip", {})
            info["streamUrl"] = ip_cfg.get("stream_url")
            info["controlBaseUrl"] = ip_cfg.get("control_base_url")
        elif camera_type == "local":
            local_cfg = config.get("local", {})
            info["preferredIndex"] = local_cfg.get("preferred_index")
        return info

    def reload(self) -> None:
        with self._lock:
            if self._camera and self._camera.is_opened():
                self._camera.release()
            self._camera = None
            self._config_cache = None

    # ------------------------------------------------------------------
    # Internal helpers
    def _get_config(self) -> Dict[str, Any]:
        if self._config_cache is None:
            manager = ConfigManager(self._config_path)
            self._config_cache = manager.get("camera", {}) or {}
        assert self._config_cache is not None
        return self._config_cache

    def _create_camera(self) -> CameraBase:
        config = self._get_config()
        camera_type = (config.get("type") or "ip").lower()

        if camera_type == "ip":
            ip_cfg = config.get("ip", {})
            stream_url = ip_cfg.get("stream_url", "http://192.168.50.254:81/stream")
            if not stream_url:
                raise RuntimeError("IP camera configuration is missing 'stream_url'.")
            control_base = ip_cfg.get("control_base_url")
            timeout = float(ip_cfg.get("timeout", 5.0))
            return IPCamera(stream_url, control_base_url=control_base, timeout=timeout)

        if camera_type == "local":
            local_cfg = config.get("local", {})
            preferred_index = local_cfg.get("preferred_index")
            return LocalCamera(preferred_index)

        raise RuntimeError(f"Unsupported camera type '{camera_type}'.")


__all__ = ["CameraManager"]
