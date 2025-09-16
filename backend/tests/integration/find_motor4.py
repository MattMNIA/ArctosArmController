"""
Test script to initialize, enable, move, and read the MKS CAN motor with CAN ID 4.
Assumes the presence of can_motor.py, mks_servo.py, and related modules in the same package.
"""

import time
import sys
import os
import can
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Direction, Enable

# Only test motor with CAN ID 4
CAN_ID = 4

# CAN bus configuration (update as needed)
CAN_INTERFACE = "slcan"  # or "socketcan", etc.
CAN_CHANNEL = "COM4"     # or "can0", etc.
CAN_BITRATE = 500000


def test_motor_4():
    print("Starting MKS CAN motor test for CAN ID 4...")
    bus = can.interface.Bus(interface=CAN_INTERFACE, channel=CAN_CHANNEL, bitrate=CAN_BITRATE)
    notifier = can.Notifier(bus, [])
    try:
        print(f"\n--- Testing motor with CAN ID {CAN_ID} ---")
        try:
            servo = MksServo(bus, notifier, CAN_ID)
            print(f"Initialized motor {CAN_ID}.")

            # Enable motor
            result = servo.enable_motor(Enable.Enable)
            print(f"Enable result: {result}")
            time.sleep(0.5)

            # Move motor (example: relative motion, update as needed)
            speed = 500
            acceleration = 50
            pulses = 1000
            move_result = servo.run_motor_relative_motion_by_pulses(Direction.CW, speed, acceleration, pulses)
            print(f"Move result: {move_result}")
            time.sleep(1)

            # Read encoder value
            try:
                pos = servo.read_encoder_value_addition()
                print(f"Motor {CAN_ID} encoder value: {pos}")
            except Exception as e:
                print(f"Error reading encoder for motor {CAN_ID}: {e}")

            # Optionally, disable motor after test
            servo.enable_motor(Enable.Disable)
            print(f"Disabled motor {CAN_ID}.")
        except Exception as e:
            print(f"Error testing motor {CAN_ID}: {e}")
    finally:
        notifier.stop()
        bus.shutdown()
        print("\nMotor test complete.")


if __name__ == "__main__":
    test_motor_4()
