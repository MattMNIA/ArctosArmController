from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Union, Any

class InputController(ABC):
    @abstractmethod
    def get_commands(self) -> Dict[Union[int, str], float]:
        """
        Returns a mapping {joint_index: velocity_command} or {'gripper': command}
        Example: {0: 0.1, 2: -0.05} means
        joint 0 increasing slowly, joint 2 decreasing slowly
        """
        pass

    @abstractmethod
    def get_events(self) -> List[Tuple[str, Any, float]]:
        """
        Returns a list of events: ('press' or 'release', joint, scale)
        Example: [('press', 0, 0.5), ('release', 2, -0.05)]
        """
        pass
