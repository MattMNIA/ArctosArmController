from abc import ABC, abstractmethod
from typing import Dict

class InputController(ABC):
    @abstractmethod
    def get_commands(self) -> Dict[int, float]:
        """
        Returns a mapping {joint_index: velocity_command}
        Example: {0: 0.1, 2: -0.05} means
        joint 0 increasing slowly, joint 2 decreasing slowly
        """
        pass
