from flask import Blueprint, request, jsonify, current_app
import logging
from core.input.keyboard_input import KeyboardController
from core.input.xbox_input import XboxController

teleop_bp = Blueprint('teleop', __name__)
logger = logging.getLogger(__name__)

# Store the teleop controller globally for now
controller = None

@teleop_bp.route('/start', methods=['POST'])
def start_teleop():
    global controller
    input_type = (request.json or {}).get('input', 'keyboard')
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({'error': 'MotionService not running'}), 500
    if input_type == 'xbox':
        controller = XboxController()
    else:
        controller = KeyboardController()
    logger.info(f"Teleop started with {input_type} input.")
    return jsonify({'status': f'Teleop started with {input_type} input.'})

@teleop_bp.route('/step', methods=['POST'])
def teleop_step():
    global controller
    motion_service = current_app.config['motion_service']
    if not motion_service.running:
        return jsonify({'error': 'MotionService not running'}), 500
    if controller is None:
        return jsonify({'error': 'Teleop not started'}), 400
    # Optionally, allow commands to be sent directly
    commands = (request.json or {}).get('commands')
    if commands:
        # Patch controller to return these commands for this step only
        orig_get_commands = controller.get_commands
        controller.get_commands = lambda: commands
        motion_service.teleop_step(controller)
        controller.get_commands = orig_get_commands
    else:
        motion_service.teleop_step(controller)
    return jsonify({'status': 'Teleop step executed'})

@teleop_bp.route('/stop', methods=['POST'])
def stop_teleop():
    global controller
    controller = None
    return jsonify({'status': 'Teleop stopped'})
