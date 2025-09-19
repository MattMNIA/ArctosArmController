import logging
import sys
import os
from pathlib import Path
import time
import can

# Add the backend path to sys.path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Enable

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # CAN bus configuration
    can_interface = "COM4"
    bitrate = 500000
    motor_id = 5

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

        # Create notifier
        notifier = can.Notifier(bus, [])

        # Create servo instance
        logger.info(f"Creating servo instance for ID {motor_id}")
        servo = MksServo(bus, notifier, motor_id)

        # Temporarily disable port remapping
        logger.info(f"Temporarily disabling port remapping for motor {motor_id}")
        result = servo.set_limit_port_remap(Enable.Disable)  # Disable port remapping
        logger.info(f"Port remap disable result for motor {motor_id}: {result}")

        # Enable motor
        logger.info(f"Enabling motor {motor_id}")
        result = servo.enable_motor(Enable.Enable)
        logger.info(f"Enable result for motor {motor_id}: {result}")
        time.sleep(0.5)  # Wait a moment for the motor to enable

        # Read enabled status
        logger.info(f"Reading enabled status for motor {motor_id}")
        status = servo.read_en_pins_status()
        logger.info(f"Enabled status for motor {motor_id}: {status}")
        time.sleep(3)
        # Re-enable port remapping
        logger.info(f"Re-enabling port remapping for motor {motor_id}")
        result = servo.set_limit_port_remap(Enable.Enable)
        logger.info(f"Port remap enable result for motor {motor_id}: {result}")

        # Read enabled status
        logger.info(f"Reading enabled status for motor {motor_id}")
        status = servo.read_en_pins_status()
        logger.info(f"Enabled status for motor {motor_id}: {status}")
    except Exception as e:
        logger.error(f"Failed to disable remapping, enable and read status for motor {motor_id}: {e}")
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