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
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.open_gripper()
    return jsonify({"status": "gripper opened"})

@exec_bp.route('/close_gripper', methods=['POST'])
def close_gripper():
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for close_gripper: {e}")
        payload = {}
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.close_gripper()
    return jsonify({"status": "gripper closed"})

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
    if not isinstance(position, (int, float)):
        return jsonify({"error": "'position' must be a number"}), 400
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({"error": "MotionService not running"}), 500
    motion_service.set_gripper_position(position)
    return jsonify({"status": f"gripper set to {position}"})


@exec_bp.route('/home_joints', methods=['POST'])
def home_joints():
    try:
        payload = request.get_json(silent=True)
    except Exception as e:
        logger.error(f"Error parsing JSON for home_joints: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not payload or 'joint_indices' not in payload:
        return jsonify({"error": "Missing 'joint_indices' in payload"}), 400
    
    joint_indices = payload['joint_indices']
    if not isinstance(joint_indices, list):
        return jsonify({"error": "'joint_indices' must be a list"}), 400
    
    # Validate that all indices are integers
    if not all(isinstance(idx, int) for idx in joint_indices):
        return jsonify({"error": "All joint indices must be integers"}), 400
    
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        logger.error("MotionService is not running")
        return jsonify({"error": "MotionService not running"}), 500
    
    motion_service.home_joints(joint_indices)
    logger.info("Home joints command enqueued: %s", joint_indices)
    return jsonify({"status": "homing joints", "joint_indices": joint_indices})

@exec_bp.route('/save_offset', methods=['POST'])
def save_offset():
    try:
        payload = request.get_json(silent=True)
    except Exception as e:
        logger.error(f"Error parsing JSON for save_offset: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    if not payload:
        return jsonify({"error": "No payload"}), 400
    
    joint_index = payload.get('joint_index')
    
    if joint_index is None or not isinstance(joint_index, int):
        return jsonify({"error": "Invalid or missing 'joint_index'"}), 400
    
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        logger.error("MotionService is not running")
        return jsonify({"error": "MotionService not running"}), 500
    
    # Get current joint position and convert to encoder units
    feedback = motion_service.driver.get_feedback()
    current_q = feedback.get("q", [])
    
    if joint_index >= len(current_q):
        return jsonify({"error": f"Joint index {joint_index} out of range"}), 400
    
    # Convert current joint angle to encoder units
    current_angle = current_q[joint_index]
    
    # Check if driver has angle_to_encoder method (only CanDriver has it)
    from core.drivers.can_driver import CanDriver
    from core.drivers.composite_driver import CompositeDriver
    
    if isinstance(motion_service.driver, CanDriver):
        encoder_value = motion_service.driver.angle_to_encoder(current_angle, joint_index)
    elif isinstance(motion_service.driver, CompositeDriver):
        # Find the CanDriver in the composite driver
        can_driver = None
        for driver in motion_service.driver.drivers:
            if isinstance(driver, CanDriver):
                can_driver = driver
                break
        if can_driver is None:
            return jsonify({"error": "No CAN driver found for encoder conversion"}), 400
        encoder_value = can_driver.angle_to_encoder(current_angle, joint_index)
    else:
        return jsonify({"error": "Driver does not support encoder conversion"}), 400
    
    # Save offset to config
    try:
        from utils.config_manager import ConfigManager
        from pathlib import Path
        
        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        config_manager = ConfigManager(config_path)
        
        # Get the motors list and find the motor with matching ID
        motors = config_manager.get('can_driver.motors', [])
        motor_config = None
        motor_index = -1
        
        for i, motor in enumerate(motors):
            if motor.get('id') == joint_index:
                motor_config = motor
                motor_index = i
                break
        
        if motor_config is None:
            return jsonify({"error": f"Motor with id {joint_index} not found in config"}), 400
        
        # Update the homing offset
        current_homing_offset = motor_config.get('homing_offset', 0)
        motor_config['homing_offset'] = -encoder_value + current_homing_offset
        motors[motor_index] = motor_config
        
        # Update the config
        config_manager.set('can_driver.motors', motors)
        config_manager.save_config()
        
        new_offset = motor_config['homing_offset']
        
        # Reload configuration in the running driver if it supports it
        try:
            if isinstance(motion_service.driver, CanDriver):
                motion_service.driver.reload_config()
                logger.info("Configuration reloaded in CanDriver")
            elif isinstance(motion_service.driver, CompositeDriver):
                # Find the CanDriver in the composite driver and reload its config
                for driver in motion_service.driver.drivers:
                    if isinstance(driver, CanDriver):
                        driver.reload_config()
                        logger.info("Configuration reloaded in CanDriver within CompositeDriver")
                        break
        except Exception as e:
            logger.warning(f"Failed to reload configuration in running driver: {e}")
        
        logger.info("Saved offset for joint %d: %d encoder units (current: %d, previous: %d, angle: %.4f rad)", 
                    joint_index, new_offset, -encoder_value, current_homing_offset, current_angle)
        return jsonify({
            "status": "offset saved",
            "joint_index": joint_index,
            "offset_encoder": new_offset,
            "current_angle": current_angle
        })
        
    except Exception as e:
        logger.error(f"Error saving offset: {e}")
        return jsonify({"error": f"Failed to save offset: {str(e)}"}), 500

@exec_bp.route('/estop', methods=['POST'])
def estop():
    """Emergency stop all motors."""
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        logger.warning("MotionService is not running, but performing emergency stop anyway")
    
    motion_service.estop()
    logger.warning("Emergency stop executed via API")
    return jsonify({"status": "emergency stop executed"})


