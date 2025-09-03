# api/exec_routes.py
from flask import Blueprint, request, jsonify, current_app
import logging
from core.motion_service import MotionCommand

logger = logging.getLogger(__name__)

exec_bp = Blueprint('exec', __name__)

@exec_bp.route('/execute', methods=['POST'])
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
    cmd = MotionCommand(q=q, duration_s=duration_s)
    motion_service.enqueue(cmd)

    logger.info("Motion command enqueued: %s", payload)
    logger.info("Command queue size: %d", motion_service.command_queue.qsize())
    return jsonify({"status": "queued", "command": payload})