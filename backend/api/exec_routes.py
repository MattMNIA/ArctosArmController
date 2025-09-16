# api/exec_routes.py
from flask import Blueprint, request, jsonify, current_app
import logging
from core.motion_service import JointCommand

logger = logging.getLogger(__name__)

exec_bp = Blueprint('execute', __name__)

@exec_bp.route('/joints', methods=['POST'])
def execute():
    try:
        payload = request.get_json(silent=True)
    except Exception as e:
        logger.error(f"Error parsing JSON for joints: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    
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
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for open_gripper: {e}")
        payload = {}
    force = payload.get('force', 50.0)
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.open_gripper(force)
    return jsonify({"status": "gripper opened", "force": force})

@exec_bp.route('/close_gripper', methods=['POST'])
def close_gripper():
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for close_gripper: {e}")
        payload = {}
    force = payload.get('force', 50.0)
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.close_gripper(force)
    return jsonify({"status": "gripper closed", "force": force})

@exec_bp.route('/set_gripper_position', methods=['POST'])
def set_gripper_position():
    try:
        payload = request.get_json(silent=True)
    except Exception as e:
        logger.error(f"Error parsing JSON for set_gripper_position: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not payload or 'position' not in payload:
        return jsonify({"error": "Missing 'position' in payload"}), 400
    position = payload['position']
    force = payload.get('force', 50.0)
    if not isinstance(position, (int, float)):
        return jsonify({"error": "'position' must be a number"}), 400
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.set_gripper_position(position, force)
    return jsonify({"status": f"gripper set to {position}", "force": force})

@exec_bp.route('/grasp_object', methods=['POST'])
def grasp_object():
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for grasp_object: {e}")
        payload = {}
    force = payload.get('force', 100.0)
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.grasp_object(force)
    return jsonify({"status": "grasping object", "force": force})

