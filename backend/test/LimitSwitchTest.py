import can
import time
import sys
import os

# Add the backend directory to the path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.MotorController import MotorController

def main():
    print("Limit Switch Test for CAN ID 01", flush=True)
    print("Press Ctrl+C to stop the test", flush=True)

    bus = None
    notifier = None

    try:
        # Initialize CAN bus (adjust interface and channel as needed)
        # For example, using slcan with COM4
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
        print("Starting limit switch monitoring...", flush=True)

        previous_limit_state = None
        last_debug_time = 0

        while True:
            try:
                # Check if at limit
                at_limit = motor.is_at_limit()
                
                # Get raw IO status for debugging
                io_status = motor.servo.read_io_port_status()
                
                # Only print when state changes or periodically for debugging
                if at_limit != previous_limit_state:
                    timestamp = time.strftime('%H:%M:%S')
                    if at_limit:
                        print(f"[{timestamp}] LIMIT SWITCH ACTIVATED! (IO Status: {io_status:08b})", flush=True)
                    else:
                        print(f"[{timestamp}] Limit switch released (IO Status: {io_status:08b})", flush=True)
                    previous_limit_state = at_limit
                
                # Print raw status every 5 seconds for debugging
                current_time = time.time()
                if current_time - last_debug_time >= 5 and io_status is not None:
                    print(f"[{time.strftime('%H:%M:%S')}] Raw IO Status: {io_status:08b} (IN_1: bit 0, IN_2: bit 1)", flush=True)
                    last_debug_time = current_time

                # Small delay to avoid overwhelming the output
                time.sleep(0.1)

            except KeyboardInterrupt:
                print("\nStopping limit switch test...")
                break
            except Exception as e:
                print(f"Error reading limit switch: {e}")
                time.sleep(1)  # Wait a bit before retrying

        print("Test completed")

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
            print("CAN bus shut down", flush=True)
        except:
            pass

if __name__ == "__main__":
    main()
