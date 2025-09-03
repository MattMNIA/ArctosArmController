import pybullet as p
import pybullet_data
import time
from typing import List, Dict, Any, Optional
import logging

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

    def home(self):
        for j in self.joint_indices:
            p.setJointMotorControl2(
                self.robot_id,
                j,
                p.POSITION_CONTROL,
                targetPosition=0.0
            )

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
        steps = int(t_s / self.time_step)
        logger.debug(f"Stepping simulation for {steps} steps")
        for _ in range(steps):
            p.stepSimulation()
            time.sleep(self.time_step)

    def get_feedback(self) -> Dict[str, Any]:
        """Return current joint positions and velocities."""
        q = []
        dq = []
        for j in self.joint_indices:
            joint_state = p.getJointState(self.robot_id, j)
            q.append(joint_state[0])   # position
            dq.append(joint_state[1])  # velocity

        return {
            "q": q,
            "dq": dq,
            "faults": [],
        }

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
        

