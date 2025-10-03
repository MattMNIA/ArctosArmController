# vision/strategies/__init__.py
from .base_strategy import BaseStrategy
from .finger_slider_strategy import FingerSliderStrategy
from .object_follow_strategy import ObjectFollowStrategy

__all__ = [
    "BaseStrategy",
    "FingerSliderStrategy",
    "ObjectFollowStrategy",
]