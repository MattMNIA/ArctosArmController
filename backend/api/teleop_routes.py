from flask import Blueprint, request, jsonify, current_app
import logging
from typing import Any, Dict

from core.teleop_manager import TeleopManager, TeleopManagerError

teleop_bp = Blueprint('teleop', __name__)
logger = logging.getLogger(__name__)


def _get_manager() -> TeleopManager:
    manager = current_app.config.get('teleop_manager')
    if manager is None:
        raise RuntimeError("Teleop manager is not configured")
    return manager


def _json_payload() -> Dict[str, Any]:
    try:
        return request.get_json(silent=True) or {}
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to parse teleop request body: %s", exc)
        return {}


@teleop_bp.route('/modes', methods=['GET'])
def list_modes():
    manager = _get_manager()
    return jsonify({'modes': manager.available_modes()})


@teleop_bp.route('/state', methods=['GET'])
def get_state():
    manager = _get_manager()
    return jsonify({'state': manager.current_state()})


@teleop_bp.route('/start', methods=['POST'])
def start_mode():
    manager = _get_manager()
    payload = _json_payload()
    mode = payload.get('mode') or payload.get('input')
    if not mode:
        return jsonify({'error': "Missing 'mode' in request body"}), 400

    options = payload.get('options')
    if not isinstance(options, dict):
        # Allow top-level keys to double as options for convenience
        options = {
            key: value
            for key, value in payload.items()
            if key not in {'mode', 'input', 'options'}
        }

    try:
        state = manager.start_mode(mode, options=options)
    except TeleopManagerError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Unexpected teleop start failure")
        return jsonify({'error': 'Failed to start teleoperation mode'}), 500

    return jsonify({'state': state})


@teleop_bp.route('/stop', methods=['POST'])
def stop_mode():
    manager = _get_manager()
    try:
        manager.stop()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unexpected teleop stop failure")
        return jsonify({'error': 'Failed to stop teleoperation mode'}), 500
    return jsonify({'state': manager.current_state()})


@teleop_bp.route('/pid', methods=['GET'])
def get_pid_values():
    """Get current PID values for object centering."""
    manager = _get_manager()
    if manager._current_mode != "object-centering":
        return jsonify({'error': 'PID tuning only available for object-centering mode'}), 400

    input_controller = manager._input_controller
    if not input_controller or not hasattr(input_controller, '_strategy'):
        return jsonify({'error': 'No active object centering strategy'}), 400

    try:
        pid_values = input_controller._strategy.get_pid_values()
        return jsonify({'pid': pid_values})
    except Exception as exc:
        logger.exception("Failed to get PID values")
        return jsonify({'error': 'Failed to retrieve PID values'}), 500


@teleop_bp.route('/pid', methods=['POST'])
def set_pid_values():
    """Update PID values for object centering."""
    manager = _get_manager()
    if manager._current_mode != "object-centering":
        return jsonify({'error': 'PID tuning only available for object-centering mode'}), 400

    input_controller = manager._input_controller
    if not input_controller or not hasattr(input_controller, '_strategy'):
        return jsonify({'error': 'No active object centering strategy'}), 400

    payload = _json_payload()
    axis = payload.get('axis')
    kp = payload.get('kp')
    ki = payload.get('ki')
    kd = payload.get('kd')

    if not axis:
        return jsonify({'error': "Missing 'axis' in request body"}), 400

    try:
        input_controller._strategy.set_pid_values(axis, kp=kp, ki=ki, kd=kd)
        # Return updated values
        pid_values = input_controller._strategy.get_pid_values()
        return jsonify({'pid': pid_values})
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to set PID values")
        return jsonify({'error': 'Failed to update PID values'}), 500
