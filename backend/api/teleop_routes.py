from flask import Blueprint, request, jsonify, current_app
import logging
from core.input.keyboard_input import KeyboardController
from core.input.xbox_input import XboxController
from core.teleop_controller import TeleopController

teleop_bp = Blueprint('teleop', __name__)
logger = logging.getLogger(__name__)

# Store the teleop controller globally for now
teleop_controller = None

@teleop_bp.route('/start', methods=['POST'])
def start_teleop():
    global teleop_controller
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for teleop start: {e}")
        payload = {}
    input_type = payload.get('input', 'keyboard')
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({'error': 'MotionService not running'}), 500
    if input_type == 'xbox':
        controller = XboxController()
    else:
        controller = KeyboardController()
    
    teleop_controller = TeleopController(controller, motion_service.driver)
    logger.info(f"Teleop started with {input_type} input.")
    return jsonify({'status': f'Teleop started with {input_type} input.'})

@teleop_bp.route('/step', methods=['POST'])
def teleop_step():
    global teleop_controller
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({'error': 'MotionService not running'}), 500
    if teleop_controller is None:
        return jsonify({'error': 'Teleop not started'}), 400
    # Optionally, allow commands to be sent directly
    try:
        payload = request.get_json(silent=True) or {}
    except Exception as e:
        logger.error(f"Error parsing JSON for teleop step: {e}")
        payload = {}
    commands = payload.get('commands')
    if commands:
        # Patch controller to return these commands for this step only
        orig_get_commands = teleop_controller.input_controller.get_commands
        teleop_controller.input_controller.get_commands = lambda: commands
        teleop_controller.teleop_step()
        teleop_controller.input_controller.get_commands = orig_get_commands
    else:
        teleop_controller.teleop_step()
    return jsonify({'status': 'Teleop step executed'})

@teleop_bp.route('/stop', methods=['POST'])
def stop_teleop():
    global teleop_controller
    if teleop_controller:
        teleop_controller.stop_all()
    teleop_controller = None
    return jsonify({'status': 'Teleop stopped'})
