import pybullet as p
import pybullet_data
import time
from typing import List, Dict, Any, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)

class PyBulletDriver:
    """
    Driver that simulates the robotic arm using PyBullet and URDF.
    Implements the same interface as other Drivers (SimDriver, CanDriver).
    """

    def __init__(self, urdf_path: str, gui: bool = True):
        """
        :param urdf_path: Path to the robot URDF file.
        :param gui: If True, launches PyBullet GUI; else runs headless.
        """
        self.urdf_path = urdf_path
        self.gui = gui
        self.physics_client: Optional[int] = None
        self.robot_id: Optional[int] = None
        self.num_joints: int = 0
        self.joint_indices: List[int] = []
        self.time_step = 1.0 / 240.0  # default PyBullet timestep
        logger.info("PyBulletDriver created with URDF: %s, GUI: %s", urdf_path, gui)
        

    def connect(self):
        if self.gui:
            self.physics_client = p.connect(p.GUI)
        else:
            self.physics_client = p.connect(p.DIRECT)

        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)

        # Load robot from URDF
        self.robot_id = p.loadURDF(
            self.urdf_path,
            useFixedBase=True
        )

        # Filter out fixed joints (type 4), keep only revolute/prismatic and optionally gripper
        self.joint_indices = [
            j for j in range(p.getNumJoints(self.robot_id))
            if p.getJointInfo(self.robot_id, j)[2] == p.JOINT_REVOLUTE
        ]
        self.num_joints = len(self.joint_indices)

        # Reset joints to zero
        for j in self.joint_indices:
            p.resetJointState(self.robot_id, j, targetValue=0.0)

        print(f"[PyBulletDriver] Loaded URDF with {self.num_joints} joints.")

    def enable(self):
        # In sim, no special enable step
        print("[PyBulletDriver] Enabled simulation")

    def disable(self):
        if self.physics_client is not None:
            p.disconnect(self.physics_client)
            print("[PyBulletDriver] Simulation stopped")

    def step_simulation(self, duration_s: float):
        """Step the PyBullet simulation for the specified duration."""
        steps = int(duration_s / self.time_step)
        logger.debug(f"Stepping simulation for {steps} steps ({duration_s}s)")
        for _ in range(steps):
            p.stepSimulation()
            time.sleep(self.time_step)

    def home(self) -> None:
        for j in self.joint_indices:
            p.setJointMotorControl2(
                self.robot_id,
                j,
                controlMode=p.POSITION_CONTROL,
                targetPosition=0.0
            )
        self.step_simulation(1.0)

    def home_joints(self, joint_indices: List[int]) -> None:
        """Home specific joints to their zero positions."""
        for joint_idx in joint_indices:
            if joint_idx < len(self.joint_indices):
                actual_joint_idx = self.joint_indices[joint_idx]
                p.setJointMotorControl2(
                    self.robot_id,
                    actual_joint_idx,
                    controlMode=p.POSITION_CONTROL,
                    targetPosition=0.0
                )
        self.step_simulation(1.0)

    def send_joint_targets(self, q: List[float], t_s: float):
        """
        Command the robot to move towards target joint positions.
        :param q: List of target joint angles (len must match num_joints).
        :param t_s: Duration to hold the command (not smooth trajectory yet).
        """
        if len(q) != self.num_joints:
            logger.error(f"Expected {self.num_joints} joints, got {len(q)}")
            raise ValueError(f"Expected {self.num_joints} joints, got {len(q)}")

        logger.info(f"Sending joint targets: {q} for {t_s} seconds")

        for j, angle in enumerate(q):
            logger.debug(f"Setting joint {j} to {angle} radians")
            p.setJointMotorControl2(
            self.robot_id,
            j,
            controlMode=p.POSITION_CONTROL,
            targetPosition=angle
            )

        # Step simulation for t_s seconds
        self.step_simulation(t_s)

    def open_gripper(self) -> None:
        """Open gripper to maximum width (0.015m separation)"""
        left_jaw_idx = 7   # jaw1 - moves in negative Z
        right_jaw_idx = 8  # jaw2 - moves in positive Z
        
        # Both jaws move to 0 (fully open)
        p.setJointMotorControl2(
            self.robot_id,
            left_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=0.0,
            force=50.0
        )
        p.setJointMotorControl2(
            self.robot_id,
            right_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=0.0,
            force=50.0
        )
        
        # Step simulation to allow movement
        self.step_simulation(0.5)
        
    def close_gripper(self) -> None:
        """Close gripper to minimum width (0.0m separation)"""
        left_jaw_idx = 7
        right_jaw_idx = 8
        
        # Both jaws move to maximum limit (fully closed)
        p.setJointMotorControl2(
            self.robot_id,
            left_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=0.015,  # URDF limit
            force=50.0
        )
        p.setJointMotorControl2(
            self.robot_id,
            right_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=0.015,  # URDF limit
            force=50.0
        )

        # Step simulation to allow movement
        self.step_simulation(0.5)

    def set_gripper_position(self, position: float) -> None:
        """Set gripper to specific opening width (0.0 to 0.015)"""
        left_jaw_idx = 7
        right_jaw_idx = 8
        
        # Clamp position to valid range
        clamped_position = max(0.0, min(position, 0.015))
        
        p.setJointMotorControl2(
            self.robot_id,
            left_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=clamped_position,
            force=50.0
        )
        p.setJointMotorControl2(
            self.robot_id,
            right_jaw_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=clamped_position,
            force=50.0
        )

        # Step simulation to allow movement
        self.step_simulation(0.05)
    
        
    def get_feedback(self) -> Dict[str, Any]:
        """Return current joint positions and velocities."""
        # Step the simulation to advance time
        p.stepSimulation()
        
        q = []
        dq = []
        for j in self.joint_indices:
            joint_state = p.getJointState(self.robot_id, j)
            q.append(joint_state[0])   # position
            dq.append(joint_state[1])  # velocity

        return {
            "q": q,
            "dq": dq,
            "error": [],
            "limits": [[False, False] for _ in self.joint_indices],
        }

    def get_camera_frame(self, width: int = 640, height: int = 480) -> np.ndarray:
        """Capture a camera frame from the PyBullet simulation."""
        view_matrix = p.computeViewMatrix(
            cameraEyePosition=[1, 1, 1],
            cameraTargetPosition=[0, 0, 0],
            cameraUpVector=[0, 0, 1]
        )
        proj_matrix = p.computeProjectionMatrixFOV(
            fov=60, aspect=float(width)/height,
            nearVal=0.1, farVal=100.0
        )
        img = p.getCameraImage(width, height, view_matrix, proj_matrix)
        rgb = np.reshape(img[2], (height, width, 4))[:, :, :3]  # take RGB
        return rgb

    def start_joint_velocity(self, joint_index: int, scale: float) -> None:
        """Start velocity control for a specific joint. Scale from -1.0 to 1.0."""
        if joint_index < 0 or joint_index >= self.num_joints:
            logger.error(f"Invalid joint index {joint_index}")
            return
        
        # Scale by default max speed (similar to CAN driver motors)
        max_speed_rpm = 200.0  # Default max speed for simulation
        speed = scale * max_speed_rpm
        
        # Convert RPM to rad/s
        speed_rad_s = speed * 2 * 3.14159 / 60
        actual_joint_idx = self.joint_indices[joint_index]
        p.setJointMotorControl2(
            self.robot_id,
            actual_joint_idx,
            controlMode=p.VELOCITY_CONTROL,
            targetVelocity=speed_rad_s
        )
        logger.debug(f"Started velocity control for joint {joint_index}: speed={speed} RPM ({speed_rad_s:.2f} rad/s)")

    def stop_joint_velocity(self, joint_index: int) -> None:
        """Stop velocity control for a specific joint."""
        if joint_index < 0 or joint_index >= self.num_joints:
            logger.error(f"Invalid joint index {joint_index}")
            return
        
        actual_joint_idx = self.joint_indices[joint_index]
        p.setJointMotorControl2(
            self.robot_id,
            actual_joint_idx,
            controlMode=p.VELOCITY_CONTROL,
            targetVelocity=0.0
        )
        logger.debug(f"Stopped velocity control for joint {joint_index}")

    def estop(self):
        """Stop motion immediately by zeroing motor torques."""
        for j in self.joint_indices:
            p.setJointMotorControl2(
                self.robot_id,
                j,
                controlMode=p.VELOCITY_CONTROL,
                force=0
            )
        print("[PyBulletDriver] EMERGENCY STOP triggered")

    def handle_limits(self, feedback: Dict[str, Any]) -> bool:
        """PyBulletDriver has no limits, so always return False."""
        return False


