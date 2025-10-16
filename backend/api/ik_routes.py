# api/ik_routes.py
from flask import Blueprint, request, jsonify

ik_bp = Blueprint('ik', __name__)

@ik_bp.route('/solve', methods=['POST'])
def solve_ik():
    from flask import current_app
    
    try:
        data = request.get_json(silent=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not data:
        return jsonify({"error": "No data"}), 400
    
    target_pose = data.get("pose")
    seed = data.get("seed", [])
    
    if not target_pose:
        return jsonify({"error": "No pose provided"}), 400
    
    # Get the IK solver from app config
    ik_solver = current_app.config.get('ik_solver')
    if not ik_solver:
        return jsonify({"error": "IK solver not available (PyBullet not installed)", "success": False}), 503
    
    try:
        result = ik_solver.solve(target_pose, seed)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"IK solve failed: {str(e)}", "success": False}), 500

@ik_bp.route('/fk', methods=['POST'])
def compute_fk():
    from flask import current_app
    
    try:
        data = request.get_json(silent=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not data:
        return jsonify({"error": "No data"}), 400
    
    joint_angles = data.get("joints", [])
    
    if not joint_angles:
        return jsonify({"error": "No joint angles provided"}), 400
    
    # Get the IK solver from app config
    ik_solver = current_app.config.get('ik_solver')
    if not ik_solver:
        return jsonify({"error": "IK solver not available (PyBullet not installed)"}), 503
    
    try:
        result = ik_solver.forward_kinematics(joint_angles)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Forward kinematics failed: {str(e)}"}), 500