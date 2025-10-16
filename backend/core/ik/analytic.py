import pybullet as p
import pybullet_data
import numpy as np
from typing import Dict, Any, List, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class AnalyticIKSolver:
    """
    Inverse Kinematics solver using PyBullet's analytic IK capabilities.
    Loads the URDF and uses PyBullet's calculateInverseKinematics for accurate solutions.
    """

    def __init__(self, urdf_path: str):
        """
        Initialize the IK solver with the URDF file.

        :param urdf_path: Path to the robot URDF file.
        """
        self.urdf_path = urdf_path
        self.physics_client: Optional[int] = None
        self.robot_id: Optional[int] = None
        self.end_effector_link_index: Optional[int] = None
        self.joint_indices: List[int] = []
        self._initialize_pybullet()

    def _initialize_pybullet(self):
        """Initialize PyBullet in DIRECT mode for IK computation."""
        try:
            self.physics_client = p.connect(p.DIRECT)
            p.setAdditionalSearchPath(pybullet_data.getDataPath())

            # Load the robot
            self.robot_id = p.loadURDF(
                self.urdf_path,
                useFixedBase=True
            )

            # Find revolute joints (arm joints)
            self.joint_indices = [
                j for j in range(p.getNumJoints(self.robot_id))
                if p.getJointInfo(self.robot_id, j)[2] == p.JOINT_REVOLUTE
            ]

            # Find the end effector link (Link_6_1, before gripper)
            for i in range(p.getNumJoints(self.robot_id)):
                joint_info = p.getJointInfo(self.robot_id, i)
                if joint_info[12].decode('utf-8') == 'Link_6_1':  # child link name
                    self.end_effector_link_index = i  # link index is the joint index
                    break

            if self.end_effector_link_index is None:
                # Fallback: assume last revolute joint's child
                if self.joint_indices:
                    last_joint = self.joint_indices[-1]
                    joint_info = p.getJointInfo(self.robot_id, last_joint)
                    self.end_effector_link_index = joint_info[1]

            logger.info(f"Initialized IK solver with {len(self.joint_indices)} joints, end effector link: {self.end_effector_link_index}")

        except Exception as e:
            logger.error(f"Failed to initialize PyBullet IK solver: {e}")
            self._cleanup()

    def _cleanup(self):
        """Clean up PyBullet resources."""
        if self.physics_client is not None:
            try:
                p.disconnect(self.physics_client)
            except:
                pass
            self.physics_client = None
            self.robot_id = None

    def solve(self, target_pose: Dict[str, Any], seed: Optional[List[float]] = None, max_iterations: int = 1000, tolerance: float = 1e-6, refinement_iterations: int = 3) -> Dict[str, Any]:
        """
        Solve inverse kinematics for the given target pose.

        :param target_pose: Dict containing 'position' [x,y,z] and 'orientation' [x,y,z,w] quaternion
        :param seed: Optional seed joint configuration
        :param max_iterations: Maximum number of iterations for convergence
        :param tolerance: Residual threshold for convergence
        :param refinement_iterations: Number of refinement iterations (FK -> IK loop)
        :return: Dict with 'joints' list, 'success' bool, 'iterations' int
        """
        if not self._is_initialized():
            return {
                "joints": [0.0] * len(self.joint_indices),
                "success": False,
                "iterations": 0,
                "error": "IK solver not initialized"
            }

        current_seed = seed
        best_result: Dict[str, Any] = {
            "joints": [0.0] * len(self.joint_indices),
            "success": False,
            "iterations": 0,
            "error": "No solution found"
        }
        best_error = float('inf')

        for refinement in range(refinement_iterations):
            try:
                # Extract position and orientation
                position = target_pose.get('position', [0, 0, 0])
                orientation = target_pose.get('orientation', [0, 0, 0, 1])  # quaternion

                # Set up the target transform
                target_position = position
                target_orientation = orientation

                # Use PyBullet's IK
                joint_angles = p.calculateInverseKinematics(
                    self.robot_id,
                    self.end_effector_link_index,
                    target_position,
                    target_orientation,
                    lowerLimits=[-2.94, -0.889, -0.628, -2.94, -2.5, -2.94],  # from URDF limits
                    upperLimits=[2.94, 1.91, 1.45, 2.94, 2.5, 2.94],
                    jointRanges=[5.88, 2.799, 2.078, 5.88, 5.0, 5.88],  # ranges
                    restPoses=current_seed if current_seed and len(current_seed) == len(self.joint_indices) else [0.0] * len(self.joint_indices),
                    maxNumIterations=max_iterations,
                    residualThreshold=tolerance
                )

                if joint_angles is None:
                    if refinement == 0:
                        return {
                            "joints": [0.0] * len(self.joint_indices),
                            "success": False,
                            "iterations": max_iterations * refinement_iterations,
                            "error": f"PyBullet IK failed to converge within {max_iterations * refinement_iterations} iterations"
                        }
                    continue

                # PyBullet returns all joint angles, but we only want the arm joints
                arm_joints = joint_angles[:len(self.joint_indices)]

                # Check accuracy by computing forward kinematics
                fk_result = self.forward_kinematics(arm_joints)
                if 'error' in fk_result:
                    continue

                # Calculate pose error
                pos_error = np.linalg.norm(np.array(fk_result['position']) - np.array(target_position))
                # Orientation error (simplified - could use quaternion distance)
                ori_error = np.linalg.norm(np.array(fk_result['orientation']) - np.array(target_orientation))
                total_error = pos_error + ori_error

                if total_error < best_error:
                    best_error = total_error
                    best_result = {
                        "joints": list(arm_joints),
                        "success": True,
                        "iterations": max_iterations * (refinement + 1),
                        "error": total_error
                    }

                # If error is small enough, return
                if total_error < tolerance:
                    return {
                        "joints": list(arm_joints),
                        "success": True,
                        "iterations": max_iterations * (refinement + 1),
                        "error": total_error
                    }

                # Use current result as seed for next iteration
                current_seed = arm_joints

            except Exception as e:
                logger.error(f"IK solve failed: {e}")
                if refinement == 0:
                    return {
                        "joints": [0.0] * len(self.joint_indices),
                        "success": False,
                        "iterations": 0,
                        "error": str(e)
                    }
                continue

        # Return best result found
        return best_result

    def _is_initialized(self) -> bool:
        """Check if the solver is properly initialized."""
        return (self.physics_client is not None and
                self.robot_id is not None and
                self.end_effector_link_index is not None)

    def forward_kinematics(self, joint_angles: List[float]) -> Dict[str, Any]:
        """
        Compute forward kinematics for the given joint angles.

        :param joint_angles: List of joint angles (len must match num_joints)
        :return: Dict with 'position' [x,y,z] and 'orientation' [x,y,z,w] quaternion
        """
        if not self._is_initialized():
            return {
                "position": [0.0, 0.0, 0.0],
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "error": "IK solver not initialized"
            }

        if len(joint_angles) != len(self.joint_indices):
            return {
                "position": [0.0, 0.0, 0.0],
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "error": f"Expected {len(self.joint_indices)} joints, got {len(joint_angles)}"
            }

        try:
            # Set joint positions
            for i, angle in enumerate(joint_angles):
                p.resetJointState(self.robot_id, self.joint_indices[i], targetValue=angle)

            # Get end-effector pose
            link_state = p.getLinkState(self.robot_id, self.end_effector_link_index)
            position = list(link_state[0])  # position
            orientation = list(link_state[1])  # orientation quaternion

            return {
                "position": position,
                "orientation": orientation
            }

        except Exception as e:
            logger.error(f"Forward kinematics failed: {e}")
            return {
                "position": [0.0, 0.0, 0.0],
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "error": str(e)
            }
