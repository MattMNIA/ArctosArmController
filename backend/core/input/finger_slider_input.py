from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .base_input import InputController
from ..vision.strategy.finger_slider_strategy import FingerSliderStrategy


class FingerSliderInput(InputController):
    """Continuous teleoperation input wrapping the finger slider strategy."""

    FINGER_TIPS = FingerSliderStrategy.FINGER_TIPS
    DEFAULT_JOINT_PAIRS = FingerSliderStrategy.DEFAULT_JOINT_PAIRS

    def __init__(
        self,
        camera_index: Optional[int] = None,
        touch_threshold: float = 0.05,
        joint_pairs: Optional[Dict[str, Tuple[int, int]]] = None,
        max_num_hands: int = 2,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.6,
        horizontal_gain: float = 2.0,
        vertical_gain: float = 2.0,
        deadzone: float = 0.05,
        update_threshold: float = 0.03,
        smoothing: float = 0.3,
        invert_left_horizontal: bool = True,
        show_window: bool = True,
        window_name: str = "Finger Slider Input",
        fullscreen: bool = False,
        allow_fullscreen_toggle: bool = True,
        enable_gestures: bool = True,
        gesture_config_path: Optional[Union[str, Path]] = None,
        min_touch_scale: float = 0.3,
        max_touch_scale: float = 2.0,
        min_hand_separation: float = 0.12,
    ) -> None:
        self._strategy = FingerSliderStrategy(
            camera_index=camera_index,
            touch_threshold=touch_threshold,
            joint_pairs=joint_pairs,
            max_num_hands=max_num_hands,
            detection_confidence=detection_confidence,
            tracking_confidence=tracking_confidence,
            horizontal_gain=horizontal_gain,
            vertical_gain=vertical_gain,
            deadzone=deadzone,
            update_threshold=update_threshold,
            smoothing=smoothing,
            invert_left_horizontal=invert_left_horizontal,
            show_window=show_window,
            window_name=window_name,
            fullscreen=fullscreen,
            allow_fullscreen_toggle=allow_fullscreen_toggle,
            enable_gestures=enable_gestures,
            gesture_config_path=gesture_config_path,
            min_touch_scale=min_touch_scale,
            max_touch_scale=max_touch_scale,
            min_hand_separation=min_hand_separation,
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
