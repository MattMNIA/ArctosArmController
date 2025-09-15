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
servo1 = MksServo(bus, notifier, 0x05)
servo2 = MksServo(bus, notifier, 0x06)
try:
    # Disable motor shaft locked-rotor protection for both servos
    # result1 = servo1.set_motor_shaft_locked_rotor_protection(Enable.Disable)
    # print(f"Servo1 disable protection result: {result1}")
    # result2 = servo2.set_motor_shaft_locked_rotor_protection(Enable.Disable)
    # print(f"Servo2 disable protection result: {result2}")

    # Enable both motors
    result1 = servo1.enable_motor(Enable.Enable)
    print(f"Servo1 enable motor result: {result1}")
    result2 = servo2.enable_motor(Enable.Enable)
    print(f"Servo2 enable motor result: {result2}")

    # Run both motors at max speed (3000 RPM) in CCW direction with max acceleration (255)
    result1 = servo1.run_motor_in_speed_mode(Direction.CCW, 30, 255)
    print(f"Servo1 run motor result: {result1}")
    result2 = servo2.run_motor_in_speed_mode(Direction.CCW, 30, 255)
    print(f"Servo2 run motor result: {result2}")

    # Wait for 10 seconds
    print("Both motors running at max speed for 10 seconds...")
    time.sleep(10)

    # Stop both motors with max acceleration
    result1 = servo1.stop_motor_in_speed_mode(255)
    print(f"Servo1 stop motor result: {result1}")
    result2 = servo2.stop_motor_in_speed_mode(255)
    print(f"Servo2 stop motor result: {result2}")

    # Wait for both motors to stop
    servo1.wait_for_motor_idle(timeout=5)
    servo2.wait_for_motor_idle(timeout=5)
    print("Both motors stopped.")

except Exception as e:
    print(f"Error: {e}")
    # Emergency stop both motors if something goes wrong
    servo1.emergency_stop_motor()
    servo2.emergency_stop_motor()

finally:
    # Clean up
    notifier.stop()
    bus.shutdown()
