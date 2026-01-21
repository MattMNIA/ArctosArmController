# api/ik_routes.py
from flask import Blueprint, request, jsonify
import numpy as np

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


@ik_bp.route('/linear_move', methods=['POST'])
def linear_move():
    """Execute a linear (straight-line) interpolated movement in Cartesian space.

    This endpoint computes waypoints along a straight line from current position
    to target position, solves IK for each waypoint, and executes them as a fluid
    trajectory by streaming position updates at regular intervals.
    """
    from flask import current_app
    import threading
    import time
    import math

    try:
        data = request.get_json(silent=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload"}), 400

    if not data:
        return jsonify({"error": "No data"}), 400

    target_pose = data.get("pose")
    num_steps = data.get("steps", 20)  # Number of interpolation steps
    duration_s = data.get("duration_s", 2.0)  # Total duration for the move

    if not target_pose:
        return jsonify({"error": "No target pose provided"}), 400

    target_position = target_pose.get("position")
    target_euler = target_pose.get("euler", [0, 0, 0])

    if not target_position or len(target_position) != 3:
        return jsonify({"error": "Invalid target position"}), 400

    # Get services
    ik_solver = current_app.config.get('ik_solver')
    motion_service = current_app.config.get('motion_service')

    if not ik_solver:
        return jsonify({"error": "IK solver not available"}), 503
    if not motion_service or not motion_service.running:
        return jsonify({"error": "Motion service not running"}), 503

    try:
        # Get current joint positions
        feedback = motion_service.driver.get_feedback()
        current_joints = feedback.get("q", [])

        if not current_joints or len(current_joints) < 6:
            return jsonify({"error": "Could not get current joint positions"}), 500

        # Get current Cartesian position via FK
        current_fk = ik_solver.forward_kinematics(current_joints)
        current_position = current_fk.get("position", [0, 0, 0])
        current_euler = current_fk.get("euler", [0, 0, 0])

        # Generate interpolated waypoints
        waypoints = []
        joint_trajectory = []

        for i in range(1, num_steps + 1):
            t = i / num_steps  # Interpolation parameter [0, 1]

            # Linear interpolation for position
            interp_position = [
                current_position[0] + t * (target_position[0] - current_position[0]),
                current_position[1] + t * (target_position[1] - current_position[1]),
                current_position[2] + t * (target_position[2] - current_position[2]),
            ]

            # Linear interpolation for orientation
            interp_euler = [
                current_euler[0] + t * (target_euler[0] - current_euler[0]),
                current_euler[1] + t * (target_euler[1] - current_euler[1]),
                current_euler[2] + t * (target_euler[2] - current_euler[2]),
            ]

            waypoints.append({
                "position": interp_position,
                "euler": interp_euler,
            })

        # Solve IK for each waypoint
        seed = current_joints

        for i, waypoint in enumerate(waypoints):
            ik_result = ik_solver.solve(waypoint, seed)

            if not ik_result.get("success", False):
                return jsonify({
                    "error": f"IK failed at waypoint {i + 1}/{num_steps}",
                    "waypoint": waypoint,
                    "success": False
                }), 400

            joint_trajectory.append(ik_result["joints"])
            seed = ik_result["joints"]  # Use solution as seed for next waypoint

        # Execute trajectory by streaming position commands in a background thread
        driver = motion_service.driver

        def execute_trajectory():
            """Stream position commands to follow the joint trajectory smoothly.

            Instead of waiting for each waypoint to complete, we continuously
            send position updates at fixed intervals with maximum acceleration.
            This creates fluid motion because motors smoothly transition to each
            new target without easing between waypoints.
            """
            dt = duration_s / num_steps  # Time between waypoints

            for i, target_joints in enumerate(joint_trajectory):
                # Compute required speed for each motor to reach next waypoint in time
                if i > 0:
                    prev_joints = joint_trajectory[i - 1]
                else:
                    prev_joints = current_joints

                # Calculate max angular distance for this segment
                max_delta = 0.0
                for j in range(len(target_joints)):
                    prev = prev_joints[j] if j < len(prev_joints) else 0.0
                    delta = abs(target_joints[j] - prev)
                    if delta > max_delta:
                        max_delta = delta

                # Calculate speed needed (rad/s -> RPM) with margin
                if max_delta > 0 and dt > 0:
                    required_rad_s = max_delta / dt
                    required_rpm = int((required_rad_s * 60.0) / (2.0 * math.pi))
                    # Add 50% margin to ensure we can keep up
                    speed_rpm = max(50, min(int(required_rpm * 1.5), 500))
                else:
                    speed_rpm = 200

                # Use send_trajectory_point for max acceleration (fluid motion)
                if hasattr(driver, 'send_trajectory_point'):
                    driver.send_trajectory_point(target_joints, speed_rpm=speed_rpm)
                else:
                    # Fallback to regular method
                    driver.send_joint_targets(target_joints)

                # Wait for the segment duration before sending next waypoint
                time.sleep(dt)

        # Start trajectory execution in background
        trajectory_thread = threading.Thread(target=execute_trajectory, daemon=True)
        trajectory_thread.start()

        return jsonify({
            "success": True,
            "status": "linear move started (position streaming)",
            "steps": num_steps,
            "duration_s": duration_s,
            "start_position": current_position,
            "end_position": target_position,
        })

    except Exception as e:
        return jsonify({"error": f"Linear move failed: {str(e)}", "success": False}), 500


@ik_bp.route('/linear_preview', methods=['POST'])
def linear_preview():
    """Preview a linear interpolated movement - returns the trajectory without executing.

    Returns the joint trajectory and Cartesian waypoints for visualization.
    """
    from flask import current_app

    try:
        data = request.get_json(silent=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload"}), 400

    if not data:
        return jsonify({"error": "No data"}), 400

    target_pose = data.get("pose")
    num_steps = data.get("steps", 10)

    if not target_pose:
        return jsonify({"error": "No target pose provided"}), 400

    target_position = target_pose.get("position")
    target_euler = target_pose.get("euler", [0, 0, 0])

    if not target_position or len(target_position) != 3:
        return jsonify({"error": "Invalid target position"}), 400

    ik_solver = current_app.config.get('ik_solver')
    motion_service = current_app.config.get('motion_service')

    if not ik_solver:
        return jsonify({"error": "IK solver not available"}), 503
    if not motion_service:
        return jsonify({"error": "Motion service not available"}), 503

    try:
        # Get current joint positions
        feedback = motion_service.driver.get_feedback()
        current_joints = feedback.get("q", [])

        if not current_joints or len(current_joints) < 6:
            return jsonify({"error": "Could not get current joint positions"}), 500

        # Get current Cartesian position via FK
        current_fk = ik_solver.forward_kinematics(current_joints)
        current_position = current_fk.get("position", [0, 0, 0])
        current_euler = current_fk.get("euler", [0, 0, 0])

        # Generate interpolated waypoints
        cartesian_waypoints = []
        joint_trajectory = []
        seed = current_joints

        for i in range(1, num_steps + 1):
            t = i / num_steps

            interp_position = [
                current_position[0] + t * (target_position[0] - current_position[0]),
                current_position[1] + t * (target_position[1] - current_position[1]),
                current_position[2] + t * (target_position[2] - current_position[2]),
            ]

            interp_euler = [
                current_euler[0] + t * (target_euler[0] - current_euler[0]),
                current_euler[1] + t * (target_euler[1] - current_euler[1]),
                current_euler[2] + t * (target_euler[2] - current_euler[2]),
            ]

            waypoint = {"position": interp_position, "euler": interp_euler}
            cartesian_waypoints.append(waypoint)

            ik_result = ik_solver.solve(waypoint, seed)

            if not ik_result.get("success", False):
                return jsonify({
                    "error": f"IK failed at waypoint {i}/{num_steps}",
                    "waypoint": waypoint,
                    "success": False,
                    "failed_at_step": i,
                }), 400

            joint_trajectory.append(ik_result["joints"])
            seed = ik_result["joints"]

        return jsonify({
            "success": True,
            "steps": num_steps,
            "start_position": current_position,
            "end_position": target_position,
            "cartesian_waypoints": cartesian_waypoints,
            "joint_trajectory": joint_trajectory,
            "final_joints": joint_trajectory[-1] if joint_trajectory else None,
        })

    except Exception as e:
        return jsonify({"error": f"Linear preview failed: {str(e)}", "success": False}), 500