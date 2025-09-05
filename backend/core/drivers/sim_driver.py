import time
from typing import List, Dict, Any

class SimDriver:
    def connect(self): print("SimDriver connected")
    def enable(self): print("SimDriver enabled")
    def disable(self): print("SimDriver disabled")
    def home(self): print("SimDriver homing")
    def send_joint_targets(self, q: List[float], t_s: float):
        print(f"SimDriver moving to {q} over {t_s:.2f}s")
    def get_feedback(self) -> Dict[str, Any]:
        return {"q": [0,0,0,0,0,0], "dq": [0,0,0,0,0,0], "faults": [], "limits": [[False, False] for _ in range(6)]}
    def estop(self): print("SimDriver ESTOP triggered")
    def open_gripper(self): print("SimDriver gripper opened")
    def close_gripper(self): print("SimDriver gripper closed")
    def set_gripper_position(self, position: float): print(f"SimDriver gripper set to {position}")
