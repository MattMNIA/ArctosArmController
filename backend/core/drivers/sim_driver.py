import time
from typing import List, Dict, Any

class SimDriver:
    def __init__(self):
        pass
    def connect(self): print("SimDriver connected")
    def enable(self): print("SimDriver enabled")
    def disable(self): print("SimDriver disabled")
    def home(self): print("SimDriver homing")
    def home_joints(self, joint_indices: List[int]): print(f"SimDriver homing joints: {joint_indices}")
    def send_joint_targets(self, q: List[float], t_s: float):
        print(f"SimDriver moving to {q} over {t_s:.2f}s")
    def get_feedback(self) -> Dict[str, Any]:
        return {"q": [0,0,0,0,0,0], "dq": [0,0,0,0,0,0], "error": [], "limits": [[False, False] for _ in range(6)]}
    def estop(self): print("SimDriver ESTOP triggered")
    def handle_limits(self, feedback: Dict[str, Any]): print(f"SimDriver handling joint limits: {feedback['limits']}")
    def close_gripper(self, force: float = 50.0): print("SimDriver gripper closed")
    def set_gripper_position(self, position: float, force: float = 50.0): print(f"SimDriver gripper set to {position}")
    def grasp_object(self, force: float = 100.0): print(f"SimDriver grasping with force {force}")
