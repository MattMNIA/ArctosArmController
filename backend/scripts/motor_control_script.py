import can
import time
import logging
import sys
import os
import argparse

# Add the backend path to sys.path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Direction, Enable

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Control a motor via CAN bus')
    parser.add_argument('--interface', default='COM4', help='CAN interface (default: COM4)')
    parser.add_argument('--id', type=int, default=4, help='Motor ID (default: 4)')
    parser.add_argument('--speed', type=int, default=500, help='Speed (0-65535, default: 500)')
    parser.add_argument('--direction', choices=['CW', 'CCW'], default='CCW', help='Direction (default: CCW)')
    parser.add_argument('--acceleration', type=int, default=100, help='Acceleration (0-255, default: 50)')
    args = parser.parse_args()

    # CAN bus configuration
    can_interface = args.interface
    bitrate = 500000

    # Motor parameters
    motor_id = args.id
    speed = args.speed
    print(f"speed = {speed}")

    acceleration = args.acceleration
    direction = Direction.CW if args.direction == 'CW' else Direction.CCW

    bus = None
    notifier = None

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
        notifier = can.Notifier(bus, [])

        # Create servo instance
        logger.info(f"Creating servo instance for ID {motor_id}")
        servo = MksServo(bus, notifier, motor_id)

        # Enable motor
        logger.info("Enabling motor")
        result = servo.enable_motor(Enable.Enable)
        logger.info(f"Motor enable result: {result}")

        # Wait a bit
        time.sleep(0.5)

        # Start motor in speed mode
        logger.info(f"Starting motor in speed mode: direction={direction}, speed={speed} RPM, acc={acceleration}")
        result = servo.run_motor_relative_motion_by_pulses(direction, speed, acceleration, 10000000)
        logger.info(f"Motor start result: {result}")

        # Keep running until user stops
        print("Motor is running. Press Ctrl+C to stop...")

        try:
            while True:
                time.sleep(1)  # Check every second
        except KeyboardInterrupt:
            logger.info("Stopping motor...")

        # Stop motor
        result = servo.stop_motor_in_speed_mode(acceleration)
        logger.info(f"Motor stop result: {result}")

        # Disable motor
        result = servo.enable_motor(Enable.Disable)
        logger.info(f"Motor disable result: {result}")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # Cleanup
        try:
            if notifier:
                notifier.stop()
            if bus:
                bus.shutdown()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

if __name__ == "__main__":
    main()
