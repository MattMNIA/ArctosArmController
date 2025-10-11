from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, current_app

from core.vision.camera_manager import CameraManager
from core.vision.cameras import IPCamera

logger = logging.getLogger(__name__)

camera_bp = Blueprint("camera", __name__)

__all__ = ["camera_bp"]


def _get_camera_manager() -> CameraManager:
    manager = current_app.config.get("camera_manager")
    if manager is None:
        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        manager = CameraManager(config_path)
        current_app.config["camera_manager"] = manager
    return manager


def _parse_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Missing required field '{field_name}'")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.lower().startswith("0x"):
            return int(value, 16)
        return int(value)
    raise ValueError(f"Field '{field_name}' must be an integer or hex string")


# ---------------------------------------------------------------------------
# Routes
@camera_bp.route("/controls", methods=["GET"])
def get_controls():
    manager = _get_camera_manager()
    try:
        camera = manager.get_camera()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to instantiate camera: %s", exc)
        return jsonify({"error": str(exc)}), 500

    controls = camera.get_supported_controls()
    try:
        values = camera.get_all_control_values()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to read camera controls: %s", exc)
        return jsonify({"error": str(exc)}), 500

    payload = [definition.to_dict(values.get(control_id, definition.default)) for control_id, definition in controls.items()]
    return jsonify({"camera": manager.describe_camera(), "controls": payload})


@camera_bp.route("/controls/<control_id>", methods=["PUT"])
def set_control(control_id: str):
    manager = _get_camera_manager()
    try:
        camera = manager.get_camera()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to instantiate camera: %s", exc)
        return jsonify({"error": str(exc)}), 500

    controls = camera.get_supported_controls()
    if control_id not in controls:
        return jsonify({"error": f"Control '{control_id}' is not supported."}), 404

    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "Request body must include 'value'."}), 400

    try:
        camera.set_control_value(control_id, payload["value"])
        value = camera.get_control_value(control_id)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to set control '%s': %s", control_id, exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"id": control_id, "value": value})


@camera_bp.route("/status", methods=["GET"])
def get_status():
    manager = _get_camera_manager()
    try:
        camera = manager.get_camera()
        values = camera.get_all_control_values()
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to fetch camera status: %s", exc)
        return jsonify({"error": str(exc)}), 500
    return jsonify(values)


@camera_bp.route("/registers/read", methods=["POST"])
def read_register():
    manager = _get_camera_manager()
    if manager.get_camera_type() != "ip":
        return jsonify({"error": "Register access is only available for IP cameras."}), 400

    camera = manager.get_camera()
    assert isinstance(camera, IPCamera)

    payload = request.get_json(silent=True) or {}
    try:
        register = _parse_int(payload.get("register"), "register")
        mask = _parse_int(payload.get("mask"), "mask")
        offset = _parse_int(payload.get("offset", 0), "offset")
        value = camera.get_register(register, mask, offset)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to read register: %s", exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"value": value, "hex": f"0x{value:x}"})


@camera_bp.route("/registers/write", methods=["POST"])
def write_register():
    manager = _get_camera_manager()
    if manager.get_camera_type() != "ip":
        return jsonify({"error": "Register access is only available for IP cameras."}), 400

    camera = manager.get_camera()
    assert isinstance(camera, IPCamera)

    payload = request.get_json(silent=True) or {}
    try:
        register = _parse_int(payload.get("register"), "register")
        mask = _parse_int(payload.get("mask"), "mask")
        value = _parse_int(payload.get("value"), "value")
        offset = _parse_int(payload.get("offset", 0), "offset")
        camera.set_register(register, mask, value, offset)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to write register: %s", exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True})


@camera_bp.route("/xclk", methods=["POST"])
def set_xclk():
    manager = _get_camera_manager()
    if manager.get_camera_type() != "ip":
        return jsonify({"error": "XCLK can only be configured for IP cameras."}), 400

    camera = manager.get_camera()
    assert isinstance(camera, IPCamera)

    payload = request.get_json(silent=True) or {}
    try:
        frequency = _parse_int(payload.get("frequency"), "frequency")
        camera.set_xclk(frequency)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to set XCLK: %s", exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True})


@camera_bp.route("/pll", methods=["POST"])
def set_pll():
    manager = _get_camera_manager()
    if manager.get_camera_type() != "ip":
        return jsonify({"error": "PLL configuration is only available for IP cameras."}), 400

    camera = manager.get_camera()
    assert isinstance(camera, IPCamera)

    payload = request.get_json(silent=True) or {}
    try:
        camera.set_pll(
            bypass=_parse_int(payload.get("bypass", 0), "bypass"),
            mul=_parse_int(payload.get("mul"), "mul"),
            sys=_parse_int(payload.get("sys"), "sys"),
            root=_parse_int(payload.get("root"), "root"),
            pre=_parse_int(payload.get("pre"), "pre"),
            seld5=_parse_int(payload.get("seld5"), "seld5"),
            pclken=_parse_int(payload.get("pclken"), "pclken"),
            pclk=_parse_int(payload.get("pclk"), "pclk"),
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to configure PLL: %s", exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True})


@camera_bp.route("/window", methods=["POST"])
def set_window():
    manager = _get_camera_manager()
    if manager.get_camera_type() != "ip":
        return jsonify({"error": "Sensor windowing is only available for IP cameras."}), 400

    camera = manager.get_camera()
    assert isinstance(camera, IPCamera)

    payload = request.get_json(silent=True) or {}
    try:
        camera.set_window(
            start_x=_parse_int(payload.get("start_x"), "start_x"),
            start_y=_parse_int(payload.get("start_y"), "start_y"),
            end_x=_parse_int(payload.get("end_x"), "end_x"),
            end_y=_parse_int(payload.get("end_y"), "end_y"),
            offset_x=_parse_int(payload.get("offset_x", 0), "offset_x"),
            offset_y=_parse_int(payload.get("offset_y", 0), "offset_y"),
            total_x=_parse_int(payload.get("total_x"), "total_x"),
            total_y=_parse_int(payload.get("total_y"), "total_y"),
            output_x=_parse_int(payload.get("output_x"), "output_x"),
            output_y=_parse_int(payload.get("output_y"), "output_y"),
            scaling=_parse_int(payload.get("scaling", 0), "scaling"),
            binning=_parse_int(payload.get("binning", 0), "binning"),
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to configure window: %s", exc)
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True})
