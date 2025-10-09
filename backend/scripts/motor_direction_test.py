"""Utility script to exercise each motor in positive and negative directions.

Usage:
    python backend/scripts/motor_direction_test.py

The script connects to the CAN driver through MotionService, then for each
motor (0-5) it spins forward for 1.5 seconds, waits for the user to continue,
spins backward for 1.5 seconds, and waits again before moving on.
"""

import sys
import time
from pathlib import Path
from typing import Optional

# Ensure the backend package is importable when running as a script
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.motion_service import MotionService
from core.drivers.can_driver import CanDriver
from core.drivers.pybullet_driver import PyBulletDriver



def _prompt(message: str) -> None:
    try:
        input(message)
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise


def exercise_motor(motion: MotionService, motor_index: int, scale: float, duration_s: float) -> None:
    driver = motion.driver
    print(f"\n===== Motor {motor_index} =====")

    print(f"Spinning motor {motor_index} in + direction for {duration_s:.1f}s...")
    driver.start_joint_velocity(motor_index, scale)
    time.sleep(duration_s)
    driver.stop_joint_velocity(motor_index)

    _prompt("Press Enter to run in the negative direction (Ctrl+C to stop)...")

    print(f"Spinning motor {motor_index} in - direction for {duration_s:.1f}s...")
    driver.start_joint_velocity(motor_index, -scale)
    time.sleep(duration_s)
    driver.stop_joint_velocity(motor_index)

    _prompt("Press Enter to continue to the next motor...")


def main(args: Optional[list[str]] = None) -> int:
    scale = 0.3  # default joint velocity scale (0-1 range)
    duration_s = 1.5

    if args is None:
        args = sys.argv[1:]

    if args:
        try:
            scale = float(args[0])
        except ValueError:
            print(f"Invalid scale '{args[0]}'. Expected a float between 0.0 and 1.0.")
            return 1
        if not 0.0 < abs(scale) <= 1.0:
            print("Scale must be in the range (0, 1].")
            return 1

    driver = CanDriver()
    driver = PyBulletDriver("backend/models/urdf/arctos_urdf.urdf", gui=True)
    motion = MotionService(driver=driver, loop_hz=20)

    print("Connecting to CAN driver via MotionService...")
    motion.start()

    try:
        _prompt("Press Enter to begin motor direction test (Ctrl+C to abort)...")
        for motor_idx in range(6):
            exercise_motor(motion, motor_idx, scale=scale, duration_s=duration_s)

        print("\nAll motors tested.")
        _prompt("Press Enter to stop MotionService and exit...")
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping early...")
    finally:
        print("Stopping MotionService...")
        motion.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
