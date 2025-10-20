"""Motor abstraction for CAN-connected servos."""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, Optional

from .mks_servo_can import mks_servo
from .mks_servo_can.mks_enums import Direction, EnableStatus
from .mks_servo_can.mks_servo import Enable

logger = logging.getLogger(__name__)


class Motor:
    """Wrapper around an MKS servo that encapsulates per-motor logic."""

    def __init__(
        self,
        motor_id: int,
        can_id: int,
        config: Dict[str, Any],
        encoder_resolution: int,
        gear_ratio: float,
    ) -> None:
        self.motor_id = motor_id
        self.can_id = can_id
        self.encoder_resolution = encoder_resolution
        self.gear_ratio = gear_ratio or 1.0
        self._config: Dict[str, Any] = dict(config or {})
        self._servo: Optional[mks_servo.MksServo] = None
        self._lock = threading.RLock()
        self._last_enable_status: Optional[EnableStatus] = None

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def nominal_speed_rpm(self) -> float:
        return self._get_float("speed_rpm", 200.0)

    @property
    def max_speed_rpm(self) -> int:
        return abs(int(self.nominal_speed_rpm))

    @property
    def acceleration(self) -> int:
        return self._get_int("acceleration", 50)

    @property
    def offset_speed(self) -> int:
        return abs(self._get_int("offset_speed", 100))

    @property
    def home_speed(self) -> int:
        return abs(self._get_int("home_speed", 50))

    @property
    def home_direction(self) -> str:
        return str(self._config.get("home_direction", "CCW"))

    @property
    def homing_offset(self) -> int:
        return self._get_int("homing_offset", 0)

    def _get_float(self, key: str, default: float) -> float:
        value = self._config.get(key, default)
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning(
                "Motor %s: invalid float config for %s, using %s",
                self.motor_id,
                key,
                default,
            )
            return float(default)

    def _get_int(self, key: str, default: int) -> int:
        value = self._config.get(key, default)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning(
                "Motor %s: invalid int config for %s, using %s",
                self.motor_id,
                key,
                default,
            )
            return int(default)

    def update_config(
        self,
        config: Dict[str, Any],
        gear_ratio: Optional[float] = None,
        encoder_resolution: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._config = dict(config or {})
            if gear_ratio is not None:
                self.gear_ratio = gear_ratio or 1.0
            if encoder_resolution is not None:
                self.encoder_resolution = encoder_resolution

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return self._servo is not None

    def initialize(self, bus, notifier, retries: int = 3, retry_delay: float = 0.5) -> bool:
        """Create and enable the underlying servo instance."""
        with self._lock:
            try:
                self._servo = mks_servo.MksServo(bus, notifier, self.can_id)
                self._servo.enable_motor(Enable.Enable)
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: failed to initialize servo: {exc}")
                self._servo = None
                return False

            for attempt in range(retries):
                try:
                    status = self._servo.read_en_pins_status()
                except Exception as exc:  # pragma: no cover - hardware failures
                    logger.warning(
                        "Motor %s: error reading enable status (attempt %s/%s): %s",
                        self.motor_id,
                        attempt + 1,
                        retries,
                        exc,
                    )
                    status = None

                endstop_triggered = False
                try:
                    io_status = self._servo.read_io_port_status()
                    endstop_triggered = io_status is not None and ((io_status & 0x01) or (io_status & 0x02))
                except Exception as exc:  # pragma: no cover - hardware failures
                    logger.debug(f"Motor {self.motor_id}: IO status read failed: {exc}")

                if status == EnableStatus.Enabled or endstop_triggered:
                    self._last_enable_status = status
                    return True

                if attempt < retries - 1:
                    logger.warning(
                        "Motor %s: enable retry %s/%s", self.motor_id, attempt + 1, retries
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "Motor %s: failed to enable after %s attempts (status=%s, endstop_triggered=%s)",
                        self.motor_id,
                        retries,
                        status,
                        endstop_triggered,
                    )
                    self._servo = None
                    return False

        return False

    def verify_enabled(self) -> bool:
        with self._lock:
            if self._servo is None:
                return False
            try:
                status = self._servo.read_en_pins_status()
                if status == EnableStatus.Enabled:
                    return True
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: enable status read failed: {exc}")
        return False

    def enable_limit_port(self) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.set_limit_port_remap(Enable.Enable)
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: failed to enable limit port: {exc}")

    def disable(self) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.disable_motor(Enable.Enable)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.warning(f"Motor {self.motor_id}: disable failed: {exc}")
            finally:
                self._servo = None

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    def angle_to_encoder(self, angle_rad: float) -> int:
        return int((angle_rad / (2 * math.pi)) * self.encoder_resolution * self.gear_ratio)

    def encoder_to_angle(self, encoder_value: int) -> float:
        return (encoder_value / (self.encoder_resolution * self.gear_ratio)) * (2 * math.pi)

    # ------------------------------------------------------------------
    # Servo interaction helpers
    # ------------------------------------------------------------------
    def read_encoder(self) -> int:
        with self._lock:
            if self._servo is None:
                return 0
            try:
                value = self._servo.read_encoder_value_addition()
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.warning(f"Motor {self.motor_id}: encoder read failed: {exc}")
                return 0
            return int(value or 0)

    def move_to_encoder(self, encoder_value: int, speed_rpm: Optional[int] = None, acceleration: Optional[int] = None) -> bool:
        with self._lock:
            if self._servo is None:
                return False
            speed = abs(int(speed_rpm if speed_rpm is not None else self.max_speed_rpm))
            acc = int(acceleration if acceleration is not None else self.acceleration)
            try:
                result = self._servo.run_motor_absolute_motion_by_axis(speed, acc, int(encoder_value))
                return result is not None
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: absolute move failed: {exc}")
                return False

    def move_to_angle(self, angle_rad: float, speed_rpm: Optional[int] = None, acceleration: Optional[int] = None) -> bool:
        encoder_value = self.angle_to_encoder(angle_rad)
        return self.move_to_encoder(encoder_value, speed_rpm, acceleration)

    def run_relative_motion(self, speed_rpm: int, acceleration: int, encoder_delta: int) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.run_motor_relative_motion_by_axis(abs(int(speed_rpm)), int(acceleration), int(encoder_delta))
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: relative move failed: {exc}")

    def run_builtin_home(self) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.b_go_home()
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: homing command failed: {exc}")

    def is_running(self) -> bool:
        with self._lock:
            if self._servo is None:
                return False
            try:
                return bool(self._servo.is_motor_running())
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: is_running check failed: {exc}")
                return False

    def set_zero(self) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.set_current_axis_to_zero()
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: failed to zero axis: {exc}")

    def run_speed_mode(self, direction: Direction, speed_rpm: int, acceleration: int) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.run_motor_in_speed_mode(direction, abs(int(speed_rpm)), int(acceleration))
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: speed mode failed: {exc}")

    def start_velocity_scale(self, scale: float, acceleration: Optional[int] = None) -> bool:
        target_rpm = scale * self.nominal_speed_rpm
        return self.start_velocity_rpm(target_rpm, acceleration)

    def start_velocity_rpm(self, rpm: float, acceleration: Optional[int] = None) -> bool:
        if rpm == 0:
            self.stop_velocity(acceleration)
            return True

        direction = Direction.CW if rpm >= 0 else Direction.CCW
        abs_speed = abs(int(rpm))
        acc = int(acceleration if acceleration is not None else self.acceleration)
        with self._lock:
            if self._servo is None:
                return False
            try:
                self._servo.run_motor_in_speed_mode(direction, abs_speed, acc)
                return True
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: velocity command failed: {exc}")
                return False

    def stop_velocity(self, acceleration: Optional[int] = 255) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.stop_motor_in_speed_mode(int(acceleration if acceleration is not None else 255))
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: stop velocity failed: {exc}")

    def direction_from_scale(self, scale: float) -> Optional[str]:
        rpm = scale * self.nominal_speed_rpm
        if rpm > 0:
            return "CW"
        if rpm < 0:
            return "CCW"
        return None

    def read_io_port_status(self) -> Optional[int]:
        with self._lock:
            if self._servo is None:
                return None
            try:
                return self._servo.read_io_port_status()
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.warning(f"Motor {self.motor_id}: IO status read failed: {exc}")
                return None

    def read_speed(self) -> float:
        with self._lock:
            if self._servo is None:
                return 0.0
            try:
                speed = self._servo.read_motor_speed()
                return float(speed if speed is not None else 0.0)
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.warning(f"Motor {self.motor_id}: speed read failed: {exc}")
                return 0.0

    def read_limits(self) -> Optional[list]:
        status = self.read_io_port_status()
        if status is None:
            return None
        in1 = not bool(status & 0x01)
        in2 = not bool((status >> 1) & 0x01)
        return [in1, in2]

    def read_shaft_angle_error(self) -> int:
        with self._lock:
            if self._servo is None:
                return 0
            try:
                error = self._servo.read_motor_shaft_angle_error()
                return int(error if error is not None else 0)
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.warning(f"Motor {self.motor_id}: shaft error read failed: {exc}")
                return 0

    def emergency_stop(self) -> None:
        with self._lock:
            if self._servo is None:
                return
            try:
                self._servo.emergency_stop_motor()
            except Exception as exc:  # pragma: no cover - hardware failures
                logger.error(f"Motor {self.motor_id}: emergency stop failed: {exc}")

