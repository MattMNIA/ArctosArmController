# core/ik/base.py
from typing import Protocol, Dict, Any, List

class IKSolver(Protocol):
    def solve(self, target_pose: Dict[str, Any], seed: List[float]) -> Dict[str, Any]:
        """Given a target pose and a seed configuration,
        return a dict with joint values and success flag.
        For MVP: just echo dummy result.
        """
        return {
            "joints": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "success": True,
            "iterations": 0
        }
