import sys
import os
import can
import time
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Direction, Enable

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Set up CAN bus - Adjust the channel and bustype according to your CAN hardware
# For Windows with PEAK CAN, use bustype='pcan', channel='PCAN_USBBUS1' or similar
# For USB2CAN, use bustype='usb2can', channel=0
# For virtual CAN on Linux, use bustype='socketcan', channel='vcan0'
bus = can.interface.Bus(
                    bustype="slcan", 
                    channel="COM4", 
                    bitrate=500000,
                    timeout=1.0
                )
# Create a notifier for incoming messages
notifier = can.Notifier(bus, [])

# Create MKS Servo instance with ID 0x04
servo = MksServo(bus, notifier, 0x04)


try:
    # Disable motor shaft locked-rotor protection
    result = servo.set_motor_shaft_locked_rotor_protection(Enable.Disable)
    print(f"Disable protection result: {result}")

    # Enable the motor
    result = servo.enable_motor(Enable.Enable)
    print(f"Enable motor result: {result}")

    # Run motor at max speed (3000 RPM) in CW direction with max acceleration (255)
    result = servo.run_motor_in_speed_mode(Direction.CCW, 50, 80)
    print(f"Run motor result: {result}")

    # Wait for 10 seconds
    print("Motor running at max speed for 10 seconds...")
    time.sleep(300)

    # Stop the motor with max acceleration
    result = servo.stop_motor_in_speed_mode(255)
    print(f"Stop motor result: {result}")

    # Wait for motor to stop
    servo.wait_for_motor_idle(timeout=5)
    print("Motor stopped.")

except Exception as e:
    print(f"Error: {e}")
    # Emergency stop if something goes wrong
    servo.emergency_stop_motor()

finally:
    # Clean up
    notifier.stop()
    bus.shutdown()
