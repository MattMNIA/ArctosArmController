import logging
import math
import time
from typing import Dict, Any, List, Optional, Protocol

class DriverProtocol(Protocol):
    """Protocol defining the driver interface for teleoperation."""
    def get_feedback(self) -> Dict[str, Any]: ...
    def send_joint_targets(self, q: List[float], t_s: Optional[float] = None) -> None: ...
    def open_gripper(self) -> None: ...
    def close_gripper(self) -> None: ...
    def set_gripper_position(self, position: float) -> None: ...
    def start_joint_velocity(self, joint_index: int, scale: float) -> None: ...
    def stop_joint_velocity(self, joint_index: int) -> None: ...
    def home_joints(self, joint_indices: List[int]) -> None: ...

# Import InputController here to avoid circular imports
from .input.base_input import InputController
from .motion_service import JointCommand
#TODO Test new teleop controller and motion service integration
logger = logging.getLogger(__name__)
class TeleopController:
    """
    Handles teleoperation input and directly controls the robotic arm.
    Manages active movements and sends commands directly to the driver.
    This provides an alternative to the queued motion service for real-time control.
    """

    def __init__(self, input_controller: InputController, driver: DriverProtocol, motion_service=None):
        self.input_controller = input_controller
        self.driver = driver
        self.motion_service = motion_service
        self.active_movements: Dict[int, float] = {}
        self.teleop_hz = 100  # Control loop frequency - increased for smoother motion
        self.gripper_position = 0.5  # Start at middle position (0.0 = closed, 1.0 = open)
        self.gripper_increment = 0.01  # How much to change position per step - reduced for finer control
        self.gripper_direction = 0  # 1 for opening, -1 for closing, 0 for stopped
        self.last_gripper_update = 0  # Track time of last gripper update
        self.velocity_refresh_interval = 0.5  # seconds between keep-alive commands
        self._last_velocity_command: Dict[int, float] = {}
        self._paused = False

    def teleop_step(self):
        """
        Process teleoperation input and control joints with velocity.
        Called repeatedly in the main control loop.
        """
        # Get events to start/stop velocities
        events = self.input_controller.get_events()
        now = time.time()
        for event, joint, scale in events:
            if isinstance(joint, str):
                if self._handle_special_event(event, joint, scale):
                    continue
            if isinstance(joint, int) and joint < 6:  # joint indices 0-5
                if self._paused:
                    if event == 'release' and joint in self.active_movements:
                        self.driver.stop_joint_velocity(joint)
                        del self.active_movements[joint]
                        self._last_velocity_command.pop(joint, None)
                    continue

                if event == 'press':
                    if abs(scale) < 1e-3:
                        if joint in self.active_movements:
                            self.driver.stop_joint_velocity(joint)
                            del self.active_movements[joint]
                            self._last_velocity_command.pop(joint, None)
                        continue

                    previous_scale = self.active_movements.get(joint)
                    if previous_scale is None or not math.isclose(previous_scale, scale, abs_tol=1e-3):
                        if previous_scale is not None:
                            self.driver.stop_joint_velocity(joint)
                        self.driver.start_joint_velocity(joint, scale)
                        self._last_velocity_command[joint] = now
                    else:
                        # Refresh timestamp without issuing duplicate command
                        self._last_velocity_command[joint] = now
                    self.active_movements[joint] = scale
                elif event == 'release':
                    self.driver.stop_joint_velocity(joint)
                    if joint in self.active_movements:
                        del self.active_movements[joint]
                    if joint in self._last_velocity_command:
                        del self._last_velocity_command[joint]
            elif joint == "gripper_open":
                if self._paused and event == 'press':
                    continue
                if event == 'press':
                    self.gripper_direction = 1  # Start opening
                elif event == 'release':
                    self.gripper_direction = 0  # Stop
            elif joint == "gripper_close":
                if self._paused and event == 'press':
                    continue
                if event == 'press':
                    self.gripper_direction = -1  # Start closing
                elif event == 'release':
                    self.gripper_direction = 0  # Stop

        # Handle incremental gripper control
        current_time = time.time()
        if self._paused:
            return

        if self.gripper_direction != 0 and (current_time - self.last_gripper_update) > 0.05:  # Update every 50ms - more frequent
            self.gripper_position += self.gripper_direction * self.gripper_increment
            self.gripper_position = max(0.0, min(1.0, self.gripper_position))  # Clamp to 0.0-1.0
            if self.motion_service:
                self.motion_service.set_gripper_position(self.gripper_position)
            else:
                self.driver.set_gripper_position(self.gripper_position)
            self.last_gripper_update = current_time

        # Maintain velocities with a heartbeat to prevent watchdogs from stopping motion
        for joint, speed in list(self.active_movements.items()):
            last_sent = self._last_velocity_command.get(joint, 0.0)
            if current_time - last_sent >= self.velocity_refresh_interval:
                self.driver.start_joint_velocity(joint, speed)
                self._last_velocity_command[joint] = current_time

    def _handle_special_event(self, event_type: str, token: str, scale: float) -> bool:
        if token == "teleop_pause":
            if event_type == 'press':
                self._pause_teleop()
            return True
        if token == "teleop_resume":
            if event_type == 'press':
                self._resume_teleop()
            return True
        if token == "zero_all_joints":
            if event_type == 'press':
                if self._paused:
                    logger.info("Teleoperation paused; ignoring zero-all request")
                else:
                    self._zero_all_joints()
            return True
        return False

    def _pause_teleop(self) -> None:
        if self._paused:
            return
        logger.info("Teleoperation paused")
        self.stop_all()
        self._paused = True
        if self.motion_service and hasattr(self.motion_service, "paused"):
            try:
                self.motion_service.paused = True
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.debug("Unable to set motion service pause flag: %s", exc)

    def _resume_teleop(self) -> None:
        if not self._paused:
            return
        logger.info("Teleoperation resumed")
        self._paused = False
        if self.motion_service and hasattr(self.motion_service, "paused"):
            try:
                self.motion_service.paused = False
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.debug("Unable to clear motion service pause flag: %s", exc)

    def _zero_all_joints(self) -> None:
        logger.info("Gesture requested zeroing joints to [0, 0, 0, 0, 0, 0]")
        self.stop_all()
        zero_targets = [0.0] * 6

        if self.motion_service and hasattr(self.motion_service, "enqueue"):
            try:
                cmd = JointCommand(q=zero_targets, duration_s=2.0)
                self.motion_service.enqueue(cmd)
                return
            except Exception as exc:
                logger.error("Failed to enqueue zero command via motion service: %s", exc)

        try:
            self.driver.send_joint_targets(zero_targets)
        except Exception as exc:
            logger.error("Driver failed to move joints to zero: %s", exc)

    def stop_all(self):
        """Stop all active teleoperation movements."""
        for joint in list(self.active_movements.keys()):
            if isinstance(joint, int):
                self.driver.stop_joint_velocity(joint)
                self._last_velocity_command.pop(joint, None)
        self.active_movements.clear()
        self.gripper_direction = 0