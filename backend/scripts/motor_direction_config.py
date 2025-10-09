"""Interactive tool to validate and configure motor direction settings.

For each CAN motor, the script:
1. Spins the motor in the positive direction.
2. Spins the motor in the negative direction.
3. Prompts you to select the desired hardware direction (CW/CCW).
4. Applies the selection via the MKS servo API and repeats the motion test.

Between phases, the script waits for you to press Enter so that you can
observe the motion safely. Use Ctrl+C at any time to abort.

Usage:
    python backend/scripts/motor_direction_config.py [scale]

The optional ``scale`` argument controls the joint velocity command magnitude
(0 < scale <= 1). The default is 0.3.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Optional

# Allow running the script directly via ``python backend/scripts/...``
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.motion_service import MotionService
from core.drivers.can_driver import CanDriver
from core.drivers.mks_servo_can.mks_enums import Direction, SuccessStatus


PROMPT_PREFIX = "[Direction Config]"
DEFAULT_SCALE = 0.3
DURATION_S = 1.5


def _prompt(message: str) -> None:
    try:
        input(f"{PROMPT_PREFIX} {message}")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        raise


def _run_velocity(driver: Any, motor_index: int, scale: float, duration_s: float) -> None:
    """Run a joint velocity command and ensure we stop afterwards."""
    driver.start_joint_velocity(motor_index, scale)
    try:
        time.sleep(duration_s)
    finally:
        driver.stop_joint_velocity(motor_index)


def _obtain_servo(driver: Any, motor_index: int):
    if not hasattr(driver, "servos"):
        return None
    servos = getattr(driver, "servos", [])
    if motor_index >= len(servos):
        return None
    return servos[motor_index]


def _choose_direction() -> Optional[Direction]:
    """Ask the user which orientation should map to positive joint commands."""
    choices = {
        "cw": Direction.CW,
        "ccw": Direction.CCW,
        "0": Direction.CW,
        "1": Direction.CCW,
    }
    prompt = (
        "Enter desired motor direction for positive joint motion "
        "[cw/ccw/skip]: "
    )
    while True:
        try:
            response = input(f"{PROMPT_PREFIX} {prompt}").strip().lower()
        except KeyboardInterrupt:
            raise
        if response in ("", "skip", "s"):
            return None
        selection = choices.get(response)
        if selection is None:
            print(
                f"{PROMPT_PREFIX} Invalid response '{response}'. "
                "Please enter 'cw', 'ccw', or 'skip'."
            )
            continue
        return selection


def _apply_direction(servo, direction: Direction) -> bool:
    result = servo.set_motor_rotation_direction(direction)
    if result is None:
        print(f"{PROMPT_PREFIX} No response from servo when setting direction.")
        return False
    if result != SuccessStatus.Success:
        print(
            f"{PROMPT_PREFIX} Servo returned {result.name} while setting direction."
        )
        return False
    print(f"{PROMPT_PREFIX} Direction updated to {direction.name}.")
    return True


def configure_motor(
    motion: MotionService,
    motor_index: int,
    scale: float,
    duration_s: float,
) -> None:
    driver = motion.driver
    servo = _obtain_servo(driver, motor_index)
    if servo is None:
        print(
            f"{PROMPT_PREFIX} Unable to access servo {motor_index}. Skipping configuration."
        )
        return

    print(f"\n===== Motor {motor_index} =====")

    keep_configuring = True
    while keep_configuring:
        _prompt(
            f"Press Enter to spin motor {motor_index} in + direction (scale={scale})."
        )
        _run_velocity(driver, motor_index, scale, duration_s)

        _prompt(
            f"Press Enter to spin motor {motor_index} in - direction (scale={scale})."
        )
        _run_velocity(driver, motor_index, -scale, duration_s)

        new_direction = _choose_direction()
        if new_direction is None:
            print(f"{PROMPT_PREFIX} Leaving motor {motor_index} direction unchanged.")
            break

        if not _apply_direction(servo, new_direction):
            retry = input(
                f"{PROMPT_PREFIX} Retry setting direction? [y/N]: "
            ).strip().lower()
            if retry == "y":
                continue
            break

        _prompt(
            "Direction updated. Press Enter to verify positive direction again."
        )
        _run_velocity(driver, motor_index, scale, duration_s)

        _prompt(
            "Press Enter to verify negative direction with updated setting."
        )
        _run_velocity(driver, motor_index, -scale, duration_s)

        satisfied = input(
            f"{PROMPT_PREFIX} Happy with motor {motor_index}? [Y/n]: "
        ).strip().lower()
        if satisfied in ("", "y", "yes"):
            keep_configuring = False

    _prompt("Press Enter to continue to the next motor...")


def parse_scale(args: list[str]) -> float:
    if not args:
        return DEFAULT_SCALE
    try:
        value = float(args[0])
    except ValueError as exc:
        raise SystemExit(f"Invalid scale '{args[0]}': {exc}")
    if not 0.0 < abs(value) <= 1.0:
        raise SystemExit("Scale must be within (0, 1].")
    return abs(value)


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    scale = parse_scale(args)

    driver = CanDriver()
    motion = MotionService(driver=driver, loop_hz=20)

    print(f"{PROMPT_PREFIX} Connecting to CAN bus via MotionService...")
    motion.start()

    try:
        _prompt(
            "Press Enter to begin motor direction configuration (Ctrl+C to abort)..."
        )
        for motor_idx in range(6):
            configure_motor(motion, motor_idx, scale=scale, duration_s=DURATION_S)
        print("\nAll motors processed.")
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping early...")
    finally:
        print(f"{PROMPT_PREFIX} Stopping MotionService...")
        motion.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
