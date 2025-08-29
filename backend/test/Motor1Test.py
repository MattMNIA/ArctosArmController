import can
import time
import sys
import os

# Add the backend directory to the path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.MotorController import MotorController

def main():
    print("Starting Motor Test for CAN ID 01", flush=True)

    bus = None
    notifier = None

    try:
        # Initialize CAN bus (adjust interface and channel as needed)
        # For example, using slcan with COM3
        bus = can.interface.Bus(interface='slcan', channel='COM4', bitrate=500000)  # type: ignore
        notifier = can.Notifier(bus, [])  # type: ignore

        # Create MotorController for CAN ID 01
        motor = MotorController(
            bus=bus,
            notifier=notifier,
            can_id=1,
            pulses_per_degree=1600,  # Default, adjust as needed
            limit_ports=(0, 1),      # IN_1 and IN_2
            scaling_factor=1.0,      # Adjust scaling if needed
            limit_active_high=False  # Set to False if limit switches are active low
        )

        print("Motor controller created", flush=True)

        # Startup the motor
        print("Initializing motor...", flush=True)
        motor.startup()
        print("Motor initialized successfully", flush=True)

        # Check initial status
        status = motor.get_status()
        initial_pos = motor.get_encoder_degrees()
        print(f"Initial motor status: {status}", flush=True)
        print(f"Initial encoder position: {initial_pos} degrees", flush=True)

        # Check if at limit
        at_limit = motor.is_at_limit()
        print(f"At limit switch: {at_limit}", flush=True)

        if not at_limit:
            # Move motor 10 degrees CW
            print("Moving motor 10 degrees CW...", flush=True)
            motor.move_degrees(10, speed=50, acceleration=20)
            after_cw_pos = motor.get_encoder_degrees()
            print("Movement completed", flush=True)
            print(f"Encoder position after CW: {after_cw_pos} degrees", flush=True)
            # Check status after movement
            status = motor.get_status()
            print(f"Motor status after movement: {status}", flush=True)

            # Move back 10 degrees CCW
            print("Moving motor back 10 degrees CCW...", flush=True)
            motor.move_degrees(-10, speed=50, acceleration=20)
            after_ccw_pos = motor.get_encoder_degrees()
            print("Movement completed", flush=True)
            print(f"Encoder position after CCW: {after_ccw_pos} degrees", flush=True)

            # Calculate position errors
            expected_final_pos = initial_pos
            actual_final_pos = after_ccw_pos
            position_error = actual_final_pos - expected_final_pos if actual_final_pos is not None and expected_final_pos is not None else None
            
            print(f"Expected final position: {expected_final_pos} degrees", flush=True)
            print(f"Actual final position: {actual_final_pos} degrees", flush=True)
            print(f"Position error: {position_error} degrees", flush=True)

            # Check status
            status = motor.get_status()
            print(f"Motor status after return: {status}", flush=True)
        else:
            print("Motor is at limit, skipping movement test", flush=True)

        # Emergency stop (just in case)
        print("Performing emergency stop...", flush=True)
        motor.stop()
        print("Emergency stop completed", flush=True)

        # Final status check
        status = motor.get_status()
        print(f"Final motor status: {status}", flush=True)

        print("Test completed successfully", flush=True)

    except Exception as e:
        print(f"Test failed with error: {e}", flush=True)
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            if notifier is not None:
                notifier.stop()
            if bus is not None:
                bus.shutdown()
            print("CAN bus shut down", flush=True)
        except:
            pass

if __name__ == "__main__":
    main()
