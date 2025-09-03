# api/exec_routes.py
from flask import Blueprint, request, jsonify

exec_bp = Blueprint('exec', __name__)

@exec_bp.route('/execute', methods=['POST'])
def execute():
    payload = request.json
    if not payload:
        return jsonify({"error": "No payload"}), 400
    # In MVP: just echo back
    
    return jsonify({"status": "queued", "command": payload})