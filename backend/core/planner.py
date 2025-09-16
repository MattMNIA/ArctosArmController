from typing import Protocol
# from .types import Limits, Trajectory, Pose, IKSolver  # Adjust the import path as needed

# class Planner(Protocol):
#     def plan_joint(
#         self, q_start: list[float], q_goal: list[float], limits: Limits
#     ) -> Trajectory:  # time-indexed waypoints (jerk-limited)
#         ...

#     def plan_cartesian(
#         self, q_start: list[float], target_pose: Pose, ik: IKSolver, limits: Limits
#     ) -> Trajectory:
#         ...
