# api/exec_routes.py
from flask import Blueprint, request, jsonify, current_app
import logging
from core.motion_service import JointCommand

logger = logging.getLogger(__name__)

exec_bp = Blueprint('execute', __name__)

@exec_bp.route('/joints', methods=['POST'])
def execute():
    payload = request.json
    logger.debug("Received payload: %s", payload)
    if not payload:
        return jsonify({"error": "No payload"}), 400
    
    q = payload.get('q')
    duration_s = payload.get('duration_s', 1.0)  # default 1 second
    
    if not q or not isinstance(q, list):
        return jsonify({"error": "Invalid joint targets 'q'"}), 400
    
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        logger.error("MotionService is not running")
        return jsonify({"error": "MotionService not running"}), 500
    cmd = JointCommand(q=q, duration_s=duration_s)
    motion_service.enqueue(cmd)

    logger.info("Motion command enqueued: %s", payload)
    logger.info("Command queue size: %d", motion_service.command_queue.qsize())
    return jsonify({"status": "queued", "command": payload})

@exec_bp.route('/open_gripper', methods=['POST'])
def open_gripper():
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.open_gripper()
    return jsonify({"status": "gripper opened"})

@exec_bp.route('/close_gripper', methods=['POST'])
def close_gripper():
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.close_gripper()
    return jsonify({"status": "gripper closed"})

@exec_bp.route('/set_gripper_position', methods=['POST'])
def set_gripper_position():
    payload = request.json
    if not payload or 'position' not in payload:
        return jsonify({"error": "Missing 'position' in payload"}), 400
    position = payload['position']
    if not isinstance(position, (int, float)):
        return jsonify({"error": "'position' must be a number"}), 400
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.set_gripper_position(position)
    return jsonify({"status": f"gripper set to {position}"})

