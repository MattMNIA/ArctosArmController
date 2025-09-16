from typing import Dict, Any, List, Optional, Union, Protocol

class DriverProtocol(Protocol):
    """Protocol defining the driver interface for teleoperation."""
    def get_feedback(self) -> Dict[str, Any]: ...
    def send_joint_targets(self, q: List[float], t_s: float) -> None: ...
    def open_gripper(self, force: float = 50.0) -> None: ...
    def close_gripper(self, force: float = 50.0) -> None: ...

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
        Process teleoperation input and send commands directly to the driver.
        Called repeatedly in the main control loop.
        """
        # Get events to update active movements
        events = self.input_controller.get_events()
        for event, joint, scale in events:
            if event == 'press':
                self.active_movements[joint] = scale
            elif event == 'release':
                if joint in self.active_movements:
                    del self.active_movements[joint]

        # Also get commands for continuous inputs like axes
        commands = self.input_controller.get_commands()
        for j, delta in commands.items():
            if abs(delta) > 0.01:  # threshold for activity
                self.active_movements[j] = delta
            else:
                if j in self.active_movements:
                    del self.active_movements[j]

        # Get current feedback to apply deltas
        feedback = self.driver.get_feedback()
        q_current = list(feedback.get("q", []))

        # Apply active movements
        joint_commands = {}
        gripper_command = None

        for j, scale in self.active_movements.items():
            if isinstance(j, int) and j < len(q_current):
                joint_commands[j] = q_current[j] + scale * 0.01  # small step for smoothness
            elif j == "gripper":
                gripper_command = scale

        # Send joint commands directly to driver if any
        if joint_commands:
            # Convert to list in joint order
            q_target = []
            for i in range(len(q_current)):
                if i in joint_commands:
                    q_target.append(joint_commands[i])
                else:
                    q_target.append(q_current[i])

            # Send directly to driver with appropriate duration
            self.driver.send_joint_targets(q_target, t_s=0.5)

        # Handle gripper commands directly
        if gripper_command is not None:
            if gripper_command > 0:
                self.driver.open_gripper(force=50.0)
            else:
                self.driver.close_gripper(force=50.0)

    def stop_all(self):
        """Stop all active teleoperation movements."""
        self.active_movements.clear()