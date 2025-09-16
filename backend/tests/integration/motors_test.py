"""
Test script to initialize, enable, move, and read each MKS CAN motor one by one.
Assumes the presence of can_motor.py, mks_servo.py, and related modules in the same package.
"""

import time
import sys
import os
import can
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from core.drivers.mks_servo_can.mks_servo import MksServo
from core.drivers.mks_servo_can.mks_enums import Direction, Enable



# List of CAN IDs to test (update as needed)
CAN_IDS = [1, 2, 3, 4, 5, 6]

# CAN bus configuration (update as needed)
CAN_INTERFACE = "slcan"  # or "socketcan", etc.
CAN_CHANNEL = "COM4"     # or "can0", etc.
CAN_BITRATE = 500000


def test_motors():
    print("Starting MKS CAN motor test...")
    bus = can.interface.Bus(interface=CAN_INTERFACE, channel=CAN_CHANNEL, bitrate=CAN_BITRATE)
    notifier = can.Notifier(bus, [])
    try:
        for can_id in CAN_IDS:
            print(f"\n--- Testing motor with CAN ID {can_id} ---")
            try:
                servo = MksServo(bus, notifier, can_id)
                print(f"Initialized motor {can_id}.")

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
                    print(f"Motor {can_id} encoder value: {pos}")
                except Exception as e:
                    print(f"Error reading encoder for motor {can_id}: {e}")

                # Optionally, disable motor after test
                servo.enable_motor(Enable.Disable)
                print(f"Disabled motor {can_id}.")
            except Exception as e:
                print(f"Error testing motor {can_id}: {e}")
    finally:
        notifier.stop()
        bus.shutdown()
        print("\nMotor test complete.")


if __name__ == "__main__":
    test_motors()
