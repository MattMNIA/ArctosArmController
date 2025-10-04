from typing import Any, Dict, List, Optional, Tuple, Union

from .base_input import InputController
from ..vision.strategy.finger_touch_strategy import FingerTouchStrategy


class FingerInput(InputController):
    """MediaPipe-powered input that maps thumb–finger touches to joint commands."""

    FINGER_TIPS = FingerTouchStrategy.FINGER_TIPS
    DEFAULT_JOINT_MAP = FingerTouchStrategy.DEFAULT_JOINT_MAP

    def __init__(
        self,
        camera_index: Optional[int] = None,
        touch_threshold: float = 0.05,
        joint_map: Optional[Dict[str, int]] = None,
        max_num_hands: int = 2,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.7,
        scale: float = 0.5,
        show_window: bool = True,
        window_name: str = "Finger Input",
        fullscreen: bool = False,
        allow_fullscreen_toggle: bool = True,
    ) -> None:
        self._strategy = FingerTouchStrategy(
            camera_index=camera_index,
            touch_threshold=touch_threshold,
            joint_map=joint_map,
            max_num_hands=max_num_hands,
            detection_confidence=detection_confidence,
            tracking_confidence=tracking_confidence,
            scale=scale,
            show_window=show_window,
            window_name=window_name,
            fullscreen=fullscreen,
            allow_fullscreen_toggle=allow_fullscreen_toggle,
        )

    @property
    def camera_index(self) -> int:
        return self._strategy.camera_index

    def get_commands(self) -> Dict[Union[int, str], float]:
        return self._strategy.get_commands()

    def get_events(self) -> List[Tuple[str, Any, float]]:
        return self._strategy.get_events()

    def close(self) -> None:
        self._strategy.close()

    def __del__(self) -> None:
        self.close()