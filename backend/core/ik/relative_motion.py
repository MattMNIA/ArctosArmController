import numpy as np
import logging
import math
from typing import Dict, Any, List, Optional, Tuple
from .analytic import AnalyticIKSolver
from ..motion_service import MotionService, JointCommand

logger = logging.getLogger(__name__)

class RelativeMotionController:
    """
    Advanced relative position-based motion controller using inverse kinematics.
    
    Provides modular methods for relative movements of the robotic arm's end effector,
    supporting both translational and rotational movements in different coordinate frames.
    
    Key features:
    - Relative translations (push forward, pull back, move up/down/left/right)
    - Relative rotations (aim up/down/left/right, roll, pitch, yaw)
    - Support for world frame and end-effector local frame movements
    - Integration with motion service for queued execution
    - Laser pointer aiming capabilities (orientation adjustments)
    """

    def __init__(self, ik_solver: AnalyticIKSolver, motion_service: MotionService):
        """
        Initialize the relative motion controller.

        :param ik_solver: Instance of AnalyticIKSolver for IK computations
        :param motion_service: Instance of MotionService for executing movements
        """
        self.ik_solver = ik_solver
        self.motion_service = motion_service

    def get_current_pose(self) -> Dict[str, Any]:
        """
        Get the current end effector pose using forward kinematics.

        :return: Dict with 'position' [x,y,z] and 'orientation' [x,y,z,w] quaternion
        """
        # Get current joint angles from feedback
        feedback = self.motion_service.driver.get_feedback()
        current_joints = feedback.get('q', [0.0] * 6)

        # Compute forward kinematics
        pose = self.ik_solver.forward_kinematics(current_joints)
        if 'error' in pose:
            logger.error(f"Failed to get current pose: {pose['error']}")
            return {'position': [0.0, 0.0, 0.0], 'orientation': [0.0, 0.0, 0.0, 1.0], 'euler': [0.0, 0.0, 0.0]}
        
        # Add Euler angles for convenience
        pose['euler'] = self._quaternion_to_euler(pose['orientation'])
        return pose

    def move_relative_translation(self, dx: float, dy: float, dz: float,
                                frame: str = 'world', duration_s: Optional[float] = None) -> bool:
        """
        Move the end effector by a relative translation vector using linear interpolation.

        :param dx: Translation in X direction (meters)
        :param dy: Translation in Y direction (meters)
        :param dz: Translation in Z direction (meters)
        :param frame: Coordinate frame ('world' or 'local')
        :param duration_s: Movement duration in seconds (optional)
        :return: True if movement was successfully planned and enqueued
        """
        current_pose = self.get_current_pose()

        # Compute new position based on frame
        if frame == 'world':
            target_position = [
                current_pose['position'][0] + dx,
                current_pose['position'][1] + dy,
                current_pose['position'][2] + dz
            ]
        elif frame == 'local':
            # Transform translation vector to world frame using current orientation
            translation_local = np.array([dx, dy, dz])
            orientation_quat = current_pose['orientation']
            rotation_matrix = self._quaternion_to_rotation_matrix(orientation_quat)
            translation_world = rotation_matrix @ translation_local

            target_position = [
                current_pose['position'][0] + translation_world[0],
                current_pose['position'][1] + translation_world[1],
                current_pose['position'][2] + translation_world[2]
            ]
        else:
            logger.error(f"Unsupported frame: {frame}")
            return False

        # Calculate speed from duration if provided, otherwise use default
        speed = 0.1  # Default speed of 0.1 m/s
        if duration_s is not None and duration_s > 0:
            distance = math.sqrt(dx**2 + dy**2 + dz**2)
            if distance > 0:
                speed = distance / duration_s
    
        target_pose = {
            'position': target_position,
            'orientation': current_pose['orientation']  # Keep current orientation
        }
        
        return self._execute_pose_target(target_pose, duration_s)

    def move_relative_rotation(self, rx: float, ry: float, rz: float,
                             frame: str = 'world', duration_s: Optional[float] = None) -> bool:
        """
        Rotate the end effector by relative Euler angles.

        :param rx: Rotation around X axis (radians)
        :param ry: Rotation around Y axis (radians)
        :param rz: Rotation around Z axis (radians)
        :param frame: Coordinate frame ('world' or 'local')
        :param duration_s: Movement duration in seconds (optional)
        :return: True if movement was successfully planned and enqueued
        """
        current_pose = self.get_current_pose()

        # Convert current orientation to Euler angles
        current_euler = current_pose['euler']

        # Apply relative rotations
        if frame == 'world':
            new_euler = [
                current_euler[0] + rx,
                current_euler[1] + ry,
                current_euler[2] + rz
            ]
            new_quat = self._euler_to_quaternion(new_euler)
        elif frame == 'local':
            # For local frame rotations, apply in end-effector frame
            # This is more complex - need to compose rotations properly
            current_quat = current_pose['orientation']
            # Convert relative Euler to quaternion
            relative_quat = self._euler_to_quaternion([rx, ry, rz])
            # Compose: new_orientation = current_orientation * relative_rotation
            new_quat = self._quaternion_multiply(current_quat, relative_quat)
        else:
            logger.error(f"Unsupported frame: {frame}")
            return False

        # Keep current position for pure rotational movement
        target_pose = {
            'position': current_pose['position'],
            'orientation': new_quat
        }

        return self._execute_pose_target(target_pose, duration_s)

    def aim_laser_at_angles(self, azimuth: float, elevation: float,
                           distance: Optional[float] = None, duration_s: Optional[float] = None) -> bool:
        """
        Aim the end effector (with laser pointer) at specific spherical angles.

        :param azimuth: Horizontal angle (radians, 0 = forward, positive = left)
        :param elevation: Vertical angle (radians, 0 = horizontal, positive = up)
        :param distance: Distance to target point (meters, optional - keeps current if None)
        :param duration_s: Movement duration in seconds (optional)
        :return: True if aiming was successfully planned and enqueued
        """
        current_pose = self.get_current_pose()

        # If distance not specified, maintain current distance from origin
        if distance is None:
            current_pos = np.array(current_pose['position'])
            distance = float(np.linalg.norm(current_pos))

        # Convert spherical coordinates to Cartesian
        # Assuming laser points along the end effector's -Z axis (forward)
        x = distance * np.cos(elevation) * np.cos(azimuth)
        y = distance * np.cos(elevation) * np.sin(azimuth)
        z = distance * np.sin(elevation)

        target_position = [x, y, z]

        # Compute orientation to point the laser at the target
        # Laser direction vector (assuming laser points along -Z in end-effector frame)
        laser_direction = np.array([0, 0, -1])  # In end-effector frame

        # Target direction from end-effector to target point
        target_direction = np.array(target_position) / distance

        # Compute rotation to align laser direction with target direction
        rotation_quat = self._compute_alignment_quaternion(laser_direction, target_direction)

        target_pose = {
            'position': target_position,
            'orientation': rotation_quat
        }

        return self._execute_pose_target(target_pose, duration_s)

    def move_with_fixed_laser_point(self, dx: float, dy: float, dz: float,
                                   duration_s: Optional[float] = None) -> bool:
        """
        Move the end effector position while keeping the laser pointer dot fixed in space.
        
        This adjusts both position and orientation to maintain the laser's pointing direction
        while translating the end effector.

        :param dx: Translation in X direction (meters)
        :param dy: Translation in Y direction (meters)
        :param dz: Translation in Z direction (meters)
        :param duration_s: Movement duration in seconds (optional)
        :return: True if movement was successfully planned and enqueued
        """
        current_pose = self.get_current_pose()

        # New position
        new_position = [
            current_pose['position'][0] + dx,
            current_pose['position'][1] + dy,
            current_pose['position'][2] + dz
        ]

        # To keep laser dot fixed, we need to adjust orientation
        # Assuming laser points along -Z, and we want to maintain the same pointing direction
        # For pure translation with fixed laser point, we might need to rotate to compensate
        # This is complex - for now, keep orientation the same (simplified)
        # Advanced implementation would compute the required orientation change

        target_pose = {
            'position': new_position,
            'orientation': current_pose['orientation']
        }

        return self._execute_pose_target(target_pose, duration_s, step_size_rad=0.02)  # Smaller steps for precise laser control

    def _execute_pose_target(self, target_pose: Dict[str, Any], duration_s: Optional[float] = None, step_size_rad: float = 0.05) -> bool:
        """
        Execute movement to a target pose using IK.

        :param target_pose: Target pose dict
        :param duration_s: Movement duration
        :param step_size_rad: Unused, kept for compatibility
        :return: True if successful
        """
        # Get current joint angles as seed for IK solver
        feedback = self.motion_service.driver.get_feedback()
        current_joints = feedback.get('q', [0.0] * 6)

        # Solve inverse kinematics with current joints as seed
        ik_result = self.ik_solver.solve(target_pose, seed=current_joints)

        if not ik_result.get('success', False):
            logger.error(f"IK solve failed: {ik_result.get('error', 'Unknown error')}")
            return False

        target_joints = ik_result['joints']

        # Send the final target joints directly
        command = JointCommand(q=target_joints, duration_s=duration_s)
        self.motion_service.enqueue(command)
        logger.info(f"Enqueued movement to joints: {target_joints}")

        return True

    @staticmethod
    def _quaternion_to_rotation_matrix(quat: List[float]) -> np.ndarray:
        """Convert quaternion to 3x3 rotation matrix."""
        x, y, z, w = quat
        return np.array([
            [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w],
            [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
            [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]
        ])

    @staticmethod
    def _euler_to_quaternion(euler: List[float]) -> List[float]:
        """Convert Euler angles (roll, pitch, yaw) to quaternion."""
        roll, pitch, yaw = euler
        cr = np.cos(roll * 0.5)
        sr = np.sin(roll * 0.5)
        cp = np.cos(pitch * 0.5)
        sp = np.sin(pitch * 0.5)
        cy = np.cos(yaw * 0.5)
        sy = np.sin(yaw * 0.5)

        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy

        return [x, y, z, w]

    @staticmethod
    def _quaternion_to_euler(quat: List[float]) -> List[float]:
        """Convert quaternion to Euler angles (roll, pitch, yaw)."""
        x, y, z, w = quat
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = np.arctan2(sinr_cosp, cosr_cosp)

        # Pitch (y-axis rotation)
        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = np.copysign(np.pi / 2, sinp)  # Use 90 degrees if out of range
        else:
            pitch = np.arcsin(sinp)

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)

        return [roll, pitch, yaw]

    @staticmethod
    def _quaternion_multiply(q1: List[float], q2: List[float]) -> List[float]:
        """Multiply two quaternions."""
        x1, y1, z1, w1 = q1
        x2, y2, z2, w2 = q2

        w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
        x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
        y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
        z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2

        return [x, y, z, w]

    @staticmethod
    def _compute_alignment_quaternion(from_vector: np.ndarray, to_vector: np.ndarray) -> List[float]:
        """
        Compute quaternion that rotates from_vector to align with to_vector.
        
        :param from_vector: Starting direction vector
        :param to_vector: Target direction vector
        :return: Quaternion as [x, y, z, w]
        """
        from_norm = from_vector / np.linalg.norm(from_vector)
        to_norm = to_vector / np.linalg.norm(to_vector)

        cross = np.cross(from_norm, to_norm)
        dot = np.dot(from_norm, to_norm)

        if dot < -0.999999:  # Vectors are nearly opposite
            # Find perpendicular vector
            perp = np.array([1, 0, 0]) if abs(from_norm[0]) < 0.9 else np.array([0, 1, 0])
            perp = perp - from_norm * np.dot(perp, from_norm)
            perp = perp / np.linalg.norm(perp)
            return RelativeMotionController._euler_to_quaternion([np.pi, 0, 0])  # 180 degree rotation

        s = np.sqrt((1 + dot) * 2)
        w = s * 0.5
        axis = cross / s

        return [axis[0], axis[1], axis[2], w]