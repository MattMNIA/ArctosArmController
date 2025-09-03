# api/exec_routes.py
from flask import Blueprint, request, jsonify, current_app
from core.motion_service import MotionCommand

exec_bp = Blueprint('exec', __name__)

@exec_bp.route('/execute', methods=['POST'])
def execute():
    payload = request.json
    if not payload:
        return jsonify({"error": "No payload"}), 400
    
    q = payload.get('q')
    duration_s = payload.get('duration_s', 1.0)  # default 1 second
    
    if not q or not isinstance(q, list):
        return jsonify({"error": "Invalid joint targets 'q'"}), 400
    
    motion_service = current_app.config['motion_service']
    cmd = MotionCommand(q=q, duration_s=duration_s)
    motion_service.enqueue(cmd)
    
    return jsonify({"status": "queued", "command": payload})