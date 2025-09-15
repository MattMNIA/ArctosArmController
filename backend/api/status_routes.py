from flask import Blueprint, request, jsonify, current_app
import logging

status_bp = Blueprint('status', __name__)


@status_bp.route('/status', methods=['GET'])
def get_status():
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    # Get latest feedback from driver
    feedback = motion_service.driver.get_feedback()
    # Compose status event (mimic _emit_status)
    event = {
        "state": motion_service.current_state,
        "q": feedback.get("q", []),
        "error": feedback.get("error", []),
        "limits": feedback.get("limits", []),
        "mode": "SIM" if motion_service.driver.__class__.__name__ == "SimDriver" else "HW"
    }
    return jsonify(event)