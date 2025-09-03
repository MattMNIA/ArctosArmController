# core/drivers/sim_driver.py
import time
from typing import List, Dict, Any

class SimDriver:
    def connect(self): print("SimDriver connected")
    def enable(self): print("SimDriver enabled")
    def disable(self): print("SimDriver disabled")
    def home(self): print("SimDriver homing")
    def send_joint_targets(self, q: List[float], t_s: float):
        print(f"SimDriver moving to {q} over {t_s:.2f}s")
        time.sleep(t_s)
    def get_feedback(self) -> Dict[str, Any]:
        return {"q": [0,0,0,0,0,0], "faults": []}
    def estop(self): print("SimDriver ESTOP triggered")
