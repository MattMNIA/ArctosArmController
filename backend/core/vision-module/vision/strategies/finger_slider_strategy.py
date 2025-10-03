from typing import Dict, Any, Optional, Tuple

from .base_strategy import BaseStrategy
from ..detectors.hand_gesture_detector import HandGestureDetector
from ..detectors.finger_tracker import FingerTracker
from ..controllers.gesture_action_router import GestureActionRouter


class FingerSliderStrategy(BaseStrategy):
    def __init__(self, gesture_action_router: GestureActionRouter, 
                 finger_tracker: FingerTracker, 
                 hand_gesture_detector: HandGestureDetector) -> None:
        super().__init__()
        self.gesture_action_router = gesture_action_router
        self.finger_tracker = finger_tracker
        self.hand_gesture_detector = hand_gesture_detector
        self.active = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False

    def execute(self) -> None:
        if not self.active:
            return

        finger_positions = self.finger_tracker.get_finger_positions()
        gesture = self.hand_gesture_detector.detect_gesture()

        if gesture:
            self.gesture_action_router.route_gesture_action(gesture)

        self.control_movement(finger_positions)

    def control_movement(self, finger_positions: Dict[str, Tuple[float, float]]) -> None:
        if 'index' in finger_positions:
            index_finger_pos = finger_positions['index']
            # Implement movement logic based on index finger position
            # For example, map position to motor control commands

        if 'middle' in finger_positions:
            middle_finger_pos = finger_positions['middle']
            # Implement additional movement logic based on middle finger position

        # Add logic for other fingers as needed

    def on_peace_sign_detected(self) -> None:
        self.stop()
        # Additional logic to handle peace sign gesture, such as stopping motors
        self.gesture_action_router.route_gesture_action("peace_sign")