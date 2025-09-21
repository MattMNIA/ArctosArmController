"""
File: core/homing.py

This module provides functions to home the robot axes and move them into a safe sleep pose.
Homing zero positions are entirely determined by offsets saved in settings (no hardcoded base zeros).
"""
import logging
import time
from typing import Any, Dict

from utils.settings_manager import SettingsManager
import threading

# Initialize module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# List of motor axes (1-based indexing corresponds to arctos.servos[axis-1])
MOTOR_IDS = [1, 2, 3, 4, 5, 6]

# Base homing sequence for independent mode (all axes)
BASE_HOMING_SEQUENCE = list(reversed(MOTOR_IDS))

# Homing sequence that will be used (can be modified based on settings)
HOMING_SEQUENCE = list(BASE_HOMING_SEQUENCE)  # Default to all axes

# Predefined sleep positions for each axis (raw units)
# TODO: Set appropriate sleep positions as needed
SLEEP_POSITIONS: Dict[int, int] = {axis: 0 for axis in MOTOR_IDS}


def update_homing_sequence(settings_manager: SettingsManager) -> None:
    """
    Update the HOMING_SEQUENCE based on the current settings.
    If coupled_axis_mode is enabled, only axes 1-4 will be homed.
    """
    global HOMING_SEQUENCE
    coupled_mode = settings_manager.get("coupled_axis_mode", False)
    if coupled_mode:
        HOMING_SEQUENCE = [axis for axis in BASE_HOMING_SEQUENCE if axis <= 4]
        logger.info("Coupled B/C axis mode detected. Homing only axes 1-4.")
    else:
        HOMING_SEQUENCE = list(BASE_HOMING_SEQUENCE)

def move_to_zero_pose(arctos: Any, settings_manager: SettingsManager, axis: int = None) -> None:
    """
    Perform true parallel homing routine using threads for all axes or a single axis.
    """
    logger.info(f"Starting parallel homing process for {'axis ' + str(axis) if axis else 'all axes'}")

    update_homing_sequence(settings_manager)
    coupled_mode = settings_manager.get("coupled_axis_mode", False)
    
    if coupled_mode:
        logger.warning("Coupled B/C axis mode is enabled. Axes 5 and 6 will not be homed automatically.")

    if axis is not None:
        if coupled_mode and axis > 4:
            logger.error(f"Cannot home axis {axis} in coupled mode")
            return
        if axis not in MOTOR_IDS:
            logger.error(f"Invalid axis {axis}")
            return
        axes_to_home = [axis]
    else:
        axes_to_home = HOMING_SEQUENCE
    
    offsets = settings_manager.get("homing_offsets", {}) or {axis: 0 for axis in MOTOR_IDS}
    speeds = settings_manager.get("joint_speeds", {})
    accelerations = settings_manager.get("joint_acceleration", {})

    servos_data = []
    threads = []

    def home_single_axis(servo, offset, speed, accel):
        try:
            servo.b_go_home()
            while servo.is_motor_running():
                time.sleep(0.05)
            
            if offset != 0:
                servo.run_motor_relative_motion_by_axis(int(speed), int(accel), -1*int(offset))
                while servo.is_motor_running():
                    time.sleep(0.05)
            
            servo.set_current_axis_to_zero()
        except Exception as e:
            logger.error(f"Error homing servo: {e}")

    try:
        # Prepare parameters for each axis
        for axis in axes_to_home:
            servo = arctos.servos[axis - 1]
            homing_settings = settings_manager.get(f"servo_{axis-1}", {})
            home_dir = homing_settings.get("home_direction", "CW")
            user_offset = offsets.get(axis - 1, 0)
            relative_offset = min(max(abs(user_offset) * (-1 if home_dir == "CCW" else 1), -8388607), 8388607)
            speed = speeds.get(axis - 1, 500)
            accel = accelerations.get(axis - 1, 150)
            
            servos_data.append((servo, relative_offset, speed, accel))

        # Start all homing threads
        for servo_data in servos_data:
            thread = threading.Thread(
                target=home_single_axis,
                args=servo_data
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        logger.info("All axes homed successfully in parallel")

    except Exception as e:
        logger.error(f"Error during parallel homing: {e}", exc_info=True)



def move_to_sleep_pose(arctos: Any, settings_manager: SettingsManager) -> None:
    """
    Move all axes to a safe sleep pose in reverse order (joint 6 to 1):
    1. Optionally move to home switch via b_go_home().
    2. Move to the predefined sleep position from SLEEP_POSITIONS.

    Args:
        arctos: Robot controller instance.
        settings_manager: SettingsManager instance for speed/accel settings.

    Returns:
        None
    """
    logger.info("Moving to sleep pose for all axes (6->1)")

    # Retrieve settings for speeds and accelerations
    speeds: Dict[int, int] = settings_manager.get("joint_speeds", {})
    accelerations: Dict[int, int] = settings_manager.get("joint_acceleration", {})

    for axis in HOMING_SEQUENCE:
        try:
            servo = arctos.servos[axis - 1]

            # Retrieve sleep position (raw units)
            sleep_pos = SLEEP_POSITIONS.get(axis, 0)
            speed = speeds.get(axis - 1, 500)
            accel = accelerations.get(axis - 1, 150)

            logger.info(
                f"Axis {axis}: moving to sleep_pos={sleep_pos}, speed={speed}, accel={accel}"
            )

            # Move to home switch first to ensure consistent start (optional)
            servo.b_go_home()
            arctos.wait_for_motors_to_stop()

            # Move to sleep position
            raw_target = sleep_pos * 100  # convert to servo raw units
            servo.run_motor_absolute_motion_by_axis(speed, accel, raw_target)
            arctos.wait_for_motors_to_stop()

            logger.info(f"Axis {axis} moved to sleep position {sleep_pos}")

        except Exception as e:
            logger.error(f"Error moving axis {axis} to sleep pose: {e}", exc_info=True)

    logger.info("All axes have reached sleep pose.")
