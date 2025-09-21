#!/usr/bin/env python3
"""
Script to restore/configure MKS servo motor with ID 05 (servo_4) with specific settings.
"""

import sys
import os
import logging
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import can
import time
from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import (
    WorkMode, Direction, Enable, EndStopLevel, HoldingStrength,
    SuccessStatus, EnableStatus
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def configure_motor_settings(servo, motor_id):
    """
    Configure motor with the specified settings for servo_4.

    Args:
        servo: MksServo instance
        motor_id: Motor ID (should be 5 for servo_4)
    """
    logger.info(f"Configuring motor ID {motor_id} with servo_4 settings...")

    # Settings for servo_4:
    # current: 1600
    # direction: CCW
    # enable_homing: Enable
    # endstop_enabled: true
    # endstop_level: Low
    # holding: FIFTHTY_PERCENT
    # home_direction: CCW
    # home_speed: 80
    # homing_offset: 25000 (not a direct servo setting, used in homing)
    # microsteps: 16
    # shaft_protect: true
    # work_mode: SrvFoc

    settings_applied = []

    try:
        # 1. Set work mode
        logger.info("Setting work mode to SrvFoc...")
        result = servo.set_work_mode(WorkMode.SrvFoc)
        if result == SuccessStatus.Success:
            logger.info("✓ Work mode set successfully")
            settings_applied.append("work_mode")
        else:
            logger.error(f"✗ Failed to set work mode: {result}")

        # 2. Set working current
        logger.info("Setting working current to 1600 mA...")
        result = servo.set_working_current(1600)
        if result == SuccessStatus.Success:
            logger.info("✓ Working current set successfully")
            settings_applied.append("current")
        else:
            logger.error(f"✗ Failed to set working current: {result}")

        # 3. Set motor rotation direction
        logger.info("Setting motor rotation direction to CCW...")
        result = servo.set_motor_rotation_direction(Direction.CCW)
        if result == SuccessStatus.Success:
            logger.info("✓ Motor direction set successfully")
            settings_applied.append("direction")
        else:
            logger.error(f"✗ Failed to set motor direction: {result}")

        # 4. Set holding current
        logger.info("Setting holding current to FIFTHTY_PERCENT...")
        result = servo.set_holding_current(HoldingStrength.FIFTHTY_PERCENT)
        if result == SuccessStatus.Success:
            logger.info("✓ Holding current set successfully")
            settings_applied.append("holding")
        else:
            logger.error(f"✗ Failed to set holding current: {result}")

        # 5. Set subdivisions (microsteps)
        logger.info("Setting subdivisions to 16...")
        result = servo.set_subdivisions(16)
        if result == SuccessStatus.Success:
            logger.info("✓ Subdivisions set successfully")
            settings_applied.append("microsteps")
        else:
            logger.error(f"✗ Failed to set subdivisions: {result}")

        # 6. Set shaft protection
        logger.info("Enabling motor shaft locked rotor protection...")
        result = servo.set_motor_shaft_locked_rotor_protection(Enable.Enable)
        if result == SuccessStatus.Success:
            logger.info("✓ Shaft protection enabled successfully")
            settings_applied.append("shaft_protect")
        else:
            logger.error(f"✗ Failed to set shaft protection: {result}")

        # 7. Set homing parameters
        logger.info("Setting homing parameters (direction=CCW, trigger=Low, speed=80)...")
        result = servo.set_home(
            homeTrig=EndStopLevel.Low,    # endstop_level: Low
            homeDir=Direction.CCW,         # home_direction: CCW
            homeSpeed=80,                  # home_speed: 80
            endLimit=Enable.Enable         # enable_homing: Enable
        )
        if result == SuccessStatus.Success:
            logger.info("✓ Homing parameters set successfully")
            settings_applied.extend(["home_direction", "endstop_level", "home_speed", "enable_homing"])
        else:
            logger.error(f"✗ Failed to set homing parameters: {result}")

        # 8. Enable limit port (for endstop_enabled: true)
        logger.info("Enabling limit port...")
        result = servo.set_limit_port_remap(Enable.Enable)
        if result == SuccessStatus.Success:
            logger.info("✓ Limit port enabled successfully")
            settings_applied.append("endstop_enabled")
        else:
            logger.error(f"✗ Failed to enable limit port: {result}")

        logger.info(f"Configuration complete. Settings applied: {settings_applied}")
        return len(settings_applied) > 0

    except Exception as e:
        logger.error(f"Error configuring motor: {e}")
        return False

def main():
    # CAN bus configuration
    can_interface = "COM4"  # Adjust as needed
    bitrate = 500000
    motor_id = 5  # Motor ID 05 (servo_4)

    logger.info(f"Restoring motor ID {motor_id} (servo_4) with specified settings...")

    bus = None
    notifier = None

    try:
        # Initialize CAN bus
        if os.name == 'nt':  # Windows
            bus = can.interface.Bus(bustype="slcan", channel=can_interface, bitrate=bitrate)
        else:  # Linux
            bus = can.interface.Bus(bustype="socketcan", channel=can_interface)

        # Create CAN notifier
        notifier = can.Notifier(bus, [])

        # Create servo instance
        servo = MksServo(bus, notifier, motor_id)

        logger.info(f"Connected to motor ID {motor_id}")

        # Enable the motor first
        logger.info("Enabling motor...")
        servo.enable_motor(Enable.Enable)

        # Wait a bit for the motor to be ready
        time.sleep(1)

        # Check if motor is enabled
        max_retries = 5
        for attempt in range(max_retries):
            status = servo.read_en_pins_status()
            logger.info(f"Motor enable status (attempt {attempt+1}): {status}")
            if status == EnableStatus.Enabled:
                break
            elif attempt < max_retries - 1:
                logger.warning(f"Motor not enabled, retrying... (attempt {attempt+1}/{max_retries})")
                time.sleep(0.5)
            else:
                logger.error("Failed to enable motor")
                return 1

        # Configure motor settings
        success = configure_motor_settings(servo, motor_id)

        if success:
            logger.info(f"✓ Motor ID {motor_id} successfully restored with servo_4 settings")
            return 0
        else:
            logger.error(f"✗ Failed to restore motor ID {motor_id}")
            return 1

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

    finally:
        # Cleanup
        try:
            if notifier is not None:
                notifier.stop()
            if bus is not None:
                bus.shutdown()
        except:
            pass

if __name__ == "__main__":
    sys.exit(main())
