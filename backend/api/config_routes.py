from flask import Blueprint, request, jsonify, current_app
import logging
from pathlib import Path
from utils.config_manager import ConfigManager

config_bp = Blueprint('config', __name__)
logger = logging.getLogger(__name__)

@config_bp.route('', methods=['GET'])
def get_config():
    """Get current configuration."""
    try:
        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        config_manager = ConfigManager(config_path)
        return jsonify(config_manager.config)
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        return jsonify({"error": str(e)}), 500

@config_bp.route('', methods=['PUT'])
def update_config():
    """Update configuration."""
    try:
        new_config = request.get_json()
        if not new_config:
            return jsonify({"error": "No config data provided"}), 400

        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        config_manager = ConfigManager(config_path)
        config_manager.config = new_config
        config_manager.save_config()

        # Notify motion service to reload config if running
        motion_service = current_app.config.get('motion_service')
        if motion_service and hasattr(motion_service.driver, 'reload_config'):
            try:
                motion_service.driver.reload_config()
                logger.info("Driver config reloaded")
            except Exception as e:
                logger.warning(f"Failed to reload driver config: {e}")

        return jsonify({"message": "Configuration updated successfully"})
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        return jsonify({"error": str(e)}), 500

@config_bp.route('/motors', methods=['GET'])
def get_motor_configs():
    """Get motor configurations."""
    try:
        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        config_manager = ConfigManager(config_path)
        motors = config_manager.get('can_driver.motors', [])
        return jsonify(motors)
    except Exception as e:
        logger.error(f"Failed to get motor configs: {e}")
        return jsonify({"error": str(e)}), 500

@config_bp.route('/motors/<int:motor_id>', methods=['PUT'])
def update_motor_config(motor_id):
    """Update a specific motor's configuration."""
    try:
        motor_config = request.get_json()
        if not motor_config:
            return jsonify({"error": "No motor config data provided"}), 400

        config_path = Path(__file__).parent.parent / "config" / "default.yml"
        config_manager = ConfigManager(config_path)

        motors = config_manager.get('can_driver.motors', [])
        if motor_id < 0 or motor_id >= len(motors):
            return jsonify({"error": f"Invalid motor ID {motor_id}"}), 400

        # Update the motor config
        motors[motor_id].update(motor_config)
        config_manager.set('can_driver.motors', motors)
        config_manager.save_config()

        # Notify motion service to reload config if running
        motion_service = current_app.config.get('motion_service')
        if motion_service and hasattr(motion_service.driver, 'reload_config'):
            try:
                motion_service.driver.reload_config()
                logger.info("Driver config reloaded")
            except Exception as e:
                logger.warning(f"Failed to reload driver config: {e}")

        return jsonify({"message": f"Motor {motor_id} configuration updated successfully"})
    except Exception as e:
        logger.error(f"Failed to update motor {motor_id} config: {e}")
        return jsonify({"error": str(e)}), 500