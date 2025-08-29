import can
import time
import sys
import os

# Add the backend directory to the path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.MotorController import MotorController

def main():
    print("Motor Positioning Calibration Test", flush=True)
    print("This test will help diagnose positioning issues", flush=True)
    print("Press Ctrl+C to stop the test", flush=True)

    bus = None
    notifier = None

    try:
        # Initialize CAN bus (adjust interface and channel as needed)
        bus = can.interface.Bus(interface='slcan', channel='COM3', bitrate=500000)  # type: ignore
        notifier = can.Notifier(bus, [])  # type: ignore

        # Create MotorController for CAN ID 01
        motor = MotorController(
            bus=bus,
            notifier=notifier,
            can_id=1,
            pulses_per_degree=1600,  # Adjust this value!
            limit_ports=(0, 1),      # IN_1 and IN_2
            scaling_factor=1.0,      # Adjust this value!
            limit_active_high=False  # Set to False if limit switches are active low
        )

        print("Motor controller created")

        # Test 1: Read initial encoder position
        print("\n=== Test 1: Initial Encoder Reading ===")
        initial_pos = motor.get_encoder_position()
        initial_degrees = motor.get_encoder_degrees()
        print(f"Raw encoder: {initial_pos}")
        print(f"Degrees: {initial_degrees}")

        # Test 2: Set position to zero
        print("\n=== Test 2: Setting Position to Zero ===")
        result = motor.set_position_to_zero()
        print(f"Zero set result: {result}")

        zero_pos = motor.get_encoder_position()
        zero_degrees = motor.get_encoder_degrees()
        print(f"After zero - Raw encoder: {zero_pos}")
        print(f"After zero - Degrees: {zero_degrees}")

        # Test 3: Small movements to test accuracy
        print("\n=== Test 3: Small Movement Test ===")
        test_angles = [1, 5, 10, -10, -5, -1]  # degrees

        for angle in test_angles:
            print(f"\nMoving {angle} degrees...")
            start_pos = motor.get_encoder_degrees()
            print(f"Start position: {start_pos} degrees")

            motor.move_degrees(angle, speed=30, acceleration=10)

            end_pos = motor.get_encoder_degrees()
            print(f"End position: {end_pos} degrees")

            expected_pos = (start_pos if start_pos is not None else 0) + angle
            error = (end_pos - expected_pos) if end_pos is not None else None
            print(f"Expected position: {expected_pos} degrees")
            print(f"Position error: {error} degrees")

            time.sleep(1)  # Brief pause

        # Test 4: Return to zero
        print("\n=== Test 4: Return to Zero ===")
        current_pos = motor.get_encoder_degrees()
        if current_pos is not None and abs(current_pos) > 0.1:
            print(f"Current position: {current_pos} degrees")
            print("Returning to zero...")
            motor.move_degrees(-current_pos, speed=30, acceleration=10)

            final_pos = motor.get_encoder_degrees()
            print(f"Final position: {final_pos} degrees")

        print("\n=== Calibration Complete ===")
        print("Check the position errors above to diagnose issues:")
        print("- Large errors suggest pulses_per_degree needs adjustment")
        print("- Different errors for CW vs CCW suggest mechanical backlash")
        print("- Consistent small errors suggest encoder resolution issues")

    except KeyboardInterrupt:
        print("\nCalibration test stopped by user")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            if notifier is not None:
                notifier.stop()
            if bus is not None:
                bus.shutdown()
            print("CAN bus shut down")
        except:
            pass

if __name__ == "__main__":
    main()
