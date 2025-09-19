import can
import time
import logging
import sys
import os

# Add the backend path to sys.path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Direction, Enable
from utils.notifier import TelegramNotifier

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_error(servo, notifier, motor_id, error):
    logger.error(f"Error detected for motor ID {motor_id}: {error}")
    notifier.send_message(f"Error detected for motor ID {motor_id}: {error}. Stopping motor.")
    try:
        servo.emergency_stop_motor()
        time.sleep(0.5)
        logger.info(f"Motor ID {motor_id} stopped and disabled due to error.")
        # Move the motor the amount of the error in the opposite direction
        try:
            opposite_direction = Direction.CCW if servo.direction == Direction.CW else Direction.CW
        except AttributeError:
            # Fallback if servo does not have a direction attribute
            opposite_direction = Direction.CCW if error > 0 else Direction.CW
        move_amount = abs(int(error))
        if move_amount > 0:
            logger.info(f"Moving motor ID {motor_id} {move_amount} pulses in the opposite direction to correct error.")
            try:
                servo.run_motor_relative_motion_by_pulses(opposite_direction, 50, 100, move_amount)
                time.sleep(0.5)
            except Exception as move_err:
                logger.error(f"Failed to move motor ID {motor_id} to correct error: {move_err}")
                notifier.send_message(f"Failed to move motor ID {motor_id} to correct error: {move_err}")
        # Restart the motor to clear the error
        logger.info(f"Restarting motor ID {motor_id} after error correction.")
        try:
            servo.enable_motor(Enable.Disable)
            time.sleep(.5)
            servo.enable_motor(Enable.Enable)
            logger.info(f"Motor ID {motor_id} restarted.")
        except Exception as restart_err:
            logger.error(f"Failed to restart motor ID {motor_id}: {restart_err}")
            notifier.send_message(f"Failed to restart motor ID {motor_id}: {restart_err}")
    except Exception as stop_err:
        logger.error(f"Failed to stop/disable motor ID {motor_id}: {stop_err}")
        notifier.send_message(f"Failed to stop/disable motor ID {motor_id}: {stop_err}")

def main():
    # CAN bus configuration
    can_interface = "COM4"
    bitrate = 500000
    logger.info(f"CAN interface: {can_interface}, Bitrate: {bitrate}")

    speed = 20
    acceleration = 100
    direction = Direction.CCW

    # Telegram notifier setup
    notifier = TelegramNotifier()

    bus = None
    notifier_instance = None
    motor_ids = [5]  # Add more motor IDs as needed
    servos = {}
    directions = {mid: Direction.CW for mid in motor_ids}

    try:
        # Initialize CAN bus
        logger.info(f"Initializing CAN bus on {can_interface}")
        bus = can.interface.Bus(
            bustype="slcan",
            channel=can_interface,
            bitrate=bitrate,
            timeout=2.0
        )

        # Create notifier (required for servo initialization)
        notifier_instance = can.Notifier(bus, [])

        for mid in motor_ids:
            logger.info(f"Creating servo instance for ID {mid}")
            servos[mid] = MksServo(bus, notifier_instance, mid)
            logger.info(f"Enabling motor {mid}")
            servos[mid].enable_motor(Enable.Enable)
            directions[mid] = Direction.CW
            servos[mid].b_go_home()
            servos[mid].wait_for_go_home()

        time.sleep(0.5)
        # Start all motors in continuous motion
        for mid in motor_ids:
            logger.info(f"Starting motor {mid} in continuous motion: direction={directions[mid]}, speed={speed} RPM, acc={acceleration}")
            servos[mid].run_motor_relative_motion_by_pulses(directions[mid], speed, acceleration, 10000)

        try:
            while True:
                for mid in motor_ids:
                    servo = servos[mid]
                    if not servo.is_motor_running():
                        time.sleep(1)
                        logger.info(f"Motor {mid} is stopped. Restarting motion.")
                        # Toggle direction for this motor
                        directions[mid] = Direction.CCW if directions[mid] == Direction.CW else Direction.CW
                        servo.run_motor_relative_motion_by_pulses(directions[mid], speed, acceleration, 10000)
                    error_value = servo.read_motor_shaft_angle_error()
                    print(f"Motor {mid} current error value: {error_value}")
                    if error_value is None:
                        logger.warning(f"Failed to read error value for motor {mid}.")
                        raise Exception(f"Failed to read error value for motor {mid}.")
                    if error_value > 2000 or error_value < -2000:
                        handle_error(servo, notifier, mid, error_value)
                        logger.warning(f"Motor {mid} error value exceeded threshold: {error_value}")
                        notifier.send_message(f"Motor ID {mid} error value exceeded threshold: {error_value}")
            time.sleep(1)  # Check every second
        except KeyboardInterrupt:
            logger.info("Stopping all motors...")

    except Exception as e:
        logger.error(f"Error: {e}")
        # Stop and disable all motors
        for mid in motor_ids:
            result = servos[mid].stop_motor_in_speed_mode(acceleration)
            logger.info(f"Motor {mid} stop result: {result}")
            result = servos[mid].enable_motor(Enable.Disable)
            logger.info(f"Motor {mid} disable result: {result}")
            
if __name__ == "__main__":
    main()