# api/ik_routes.py
from flask import Blueprint, request, jsonify
from core.ik.base import IKSolver

ik_bp = Blueprint('ik', __name__)

@ik_bp.route('/solve', methods=['POST'])
def solve_ik():
    try:
        data = request.get_json(silent=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not data:
        return jsonify({"error": "No data"}), 400
    target_pose = data.get("pose")
    seed = data.get("seed", [])
    # Note: IKSolver is a Protocol, cannot instantiate directly.
    # Placeholder: return a stub result
    result = {"joints": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}  # stub
    return jsonify(result)