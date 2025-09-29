from typing import Dict, Any, List, Optional, Union, Protocol

class DriverProtocol(Protocol):
    """Protocol defining the driver interface for teleoperation."""
    def get_feedback(self) -> Dict[str, Any]: ...
    def send_joint_targets(self, q: List[float], t_s: float) -> None: ...
    def open_gripper(self) -> None: ...
    def close_gripper(self) -> None: ...
    def set_gripper_position(self, position: float) -> None: ...
    def start_joint_velocity(self, joint_index: int, scale: float) -> None: ...
    def stop_joint_velocity(self, joint_index: int) -> None: ...

# Import InputController here to avoid circular imports
from .input.base_input import InputController

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
        self.active_movements: Dict[Any, float] = {}
        self.teleop_hz = 100  # Control loop frequency - increased for smoother motion
        self.gripper_position = 0.5  # Start at middle position (0.0 = closed, 1.0 = open)
        self.gripper_increment = 0.01  # How much to change position per step - reduced for finer control
        self.gripper_direction = 0  # 1 for opening, -1 for closing, 0 for stopped
        self.last_gripper_update = 0  # Track time of last gripper update

    def teleop_step(self):
        """
        Process teleoperation input and control joints with velocity.
        Called repeatedly in the main control loop.
        """
        import time
        
        # Get events to start/stop velocities
        events = self.input_controller.get_events()
        for event, joint, scale in events:
            if isinstance(joint, int) and joint < 6:  # joint indices 0-5
                if event == 'press':
                    # Pass scale (-1 to 1) directly to driver for motor-specific scaling
                    self.driver.start_joint_velocity(joint, scale)
                    self.active_movements[joint] = scale
                elif event == 'release':
                    self.driver.stop_joint_velocity(joint)
                    if joint in self.active_movements:
                        del self.active_movements[joint]
            elif joint == "gripper_open":
                if event == 'press':
                    self.gripper_direction = 1  # Start opening
                elif event == 'release':
                    self.gripper_direction = 0  # Stop
            elif joint == "gripper_close":
                if event == 'press':
                    self.gripper_direction = -1  # Start closing
                elif event == 'release':
                    self.gripper_direction = 0  # Stop

        # Handle incremental gripper control
        current_time = time.time()
        if self.gripper_direction != 0 and (current_time - self.last_gripper_update) > 0.05:  # Update every 50ms - more frequent
            self.gripper_position += self.gripper_direction * self.gripper_increment
            self.gripper_position = max(0.0, min(1.0, self.gripper_position))  # Clamp to 0.0-1.0
            if self.motion_service:
                self.motion_service.set_gripper_position(self.gripper_position)
            else:
                self.driver.set_gripper_position(self.gripper_position)
            self.last_gripper_update = current_time

        # Maintain velocities for active movements (needed for PyBullet)
        for joint, speed in self.active_movements.items():
            if isinstance(joint, int):
                self.driver.start_joint_velocity(joint, speed)

    def stop_all(self):
        """Stop all active teleoperation movements."""
        for joint in list(self.active_movements.keys()):
            if isinstance(joint, int):
                self.driver.stop_joint_velocity(joint)
        self.active_movements.clear()