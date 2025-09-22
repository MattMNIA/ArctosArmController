from typing import Dict, Any, List, Optional, Union, Protocol

class DriverProtocol(Protocol):
    """Protocol defining the driver interface for teleoperation."""
    def get_feedback(self) -> Dict[str, Any]: ...
    def send_joint_targets(self, q: List[float], t_s: float) -> None: ...
    def open_gripper(self, force: float = 50.0) -> None: ...
    def close_gripper(self, force: float = 50.0) -> None: ...
    def start_joint_velocity(self, joint_index: int, speed: float) -> None: ...
    def stop_joint_velocity(self, joint_index: int) -> None: ...

# Import InputController here to avoid circular imports
from .input.base_input import InputController

class TeleopController:
    """
    Handles teleoperation input and directly controls the robotic arm.
    Manages active movements and sends commands directly to the driver.
    This provides an alternative to the queued motion service for real-time control.
    """

    def __init__(self, input_controller: InputController, driver: DriverProtocol):
        self.input_controller = input_controller
        self.driver = driver
        self.active_movements: Dict[Any, float] = {}
        self.teleop_hz = 50  # Control loop frequency

    def teleop_step(self):
        """
        Process teleoperation input and control joints with velocity.
        Called repeatedly in the main control loop.
        """
        # Get events to start/stop velocities
        events = self.input_controller.get_events()
        for event, joint, scale in events:
            if isinstance(joint, int) and joint < 6:  # joint indices 0-5
                if event == 'press':
                    # Convert scale to speed (RPM), adjust factor as needed
                    speed = scale * 10.0  # scale from keyboard is like 10, make speed 500 RPM max
                    self.driver.start_joint_velocity(joint, speed)
                    self.active_movements[joint] = speed
                elif event == 'release':
                    self.driver.stop_joint_velocity(joint)
                    if joint in self.active_movements:
                        del self.active_movements[joint]
            elif joint == "gripper":
                if event == 'press':
                    if scale > 0:
                        self.driver.open_gripper(force=50.0)
                    else:
                        self.driver.close_gripper(force=50.0)

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