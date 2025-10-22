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


@teleop_bp.route('/pause', methods=['POST'])
def pause_mode():
    manager = _get_manager()
    try:
        state = manager.pause()
    except TeleopManagerError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.exception("Unexpected pause failure")
        return jsonify({'error': 'Failed to pause teleoperation mode'}), 500
    return jsonify({'state': state})


@teleop_bp.route('/resume', methods=['POST'])
def resume_mode():
    manager = _get_manager()
    try:
        state = manager.resume()
    except TeleopManagerError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.exception("Unexpected resume failure")
        return jsonify({'error': 'Failed to resume teleoperation mode'}), 500
    return jsonify({'state': state})
