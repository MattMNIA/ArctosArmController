"""
Movement validation utilities for MKS servos
"""
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def verify_motor_movement(servo, initial_pos: int, expected_offset: int, timeout: float = 5.0) -> tuple[bool, Optional[str]]:
    """
    Verifies that a motor has moved the expected distance.
    
    Args:
        servo: The MksServo instance
        initial_pos: The initial position before movement
        expected_offset: The expected relative movement distance
        timeout: Maximum time to wait for movement to complete in seconds

    Returns:
        tuple[bool, Optional[str]]: (success, error_message if any)
    """
    # Wait for movement to complete
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < timeout:
        if not servo.is_motor_running():
            break
        time.sleep(0.1)
    else:
        return False, "Timeout waiting for motor movement to complete"

    # Get final position
    final_pos = servo.read_encoder_value_addition()
    actual_movement = final_pos - initial_pos

    # Check if movement was within tolerance (±100 pulses)
    if abs(abs(actual_movement) - abs(expected_offset)) > 100:
        error_msg = (
            f"Movement verification failed:\n"
            f"  Expected movement: {expected_offset}\n"
            f"  Actual movement: {actual_movement}\n"
            f"  Start position: {initial_pos}\n"
            f"  End position: {final_pos}"
        )
        logger.warning(error_msg)
        return False, error_msg

    return True, None
