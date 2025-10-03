from typing import Dict, Tuple, Any
import cv2
import mediapipe as mp
from .base_detector import BaseDetector

class FingerTracker(BaseDetector):
    """Detects finger positions and movements using MediaPipe."""

    def __init__(self, max_num_hands: int = 2, detection_confidence: float = 0.7, tracking_confidence: float = 0.7) -> None:
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._drawing_utils = mp.solutions.drawing_utils

    def process_frame(self, frame: Any) -> Dict[str, Any]:
        """Processes a single frame and returns detected finger positions."""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb_frame)

        if results.multi_hand_landmarks:
            return self._extract_finger_positions(results)
        return {}

    def _extract_finger_positions(self, results) -> Dict[str, Tuple[float, float]]:
        """Extracts finger positions from the detection results."""
        finger_positions = {}
        for hand_landmarks in results.multi_hand_landmarks:
            for finger_name, tip_idx in self.FINGER_TIPS.items():
                landmark = hand_landmarks.landmark[tip_idx]
                finger_positions[finger_name] = (landmark.x, landmark.y)
        return finger_positions

    def draw_landmarks(self, frame: Any) -> None:
        """Draws hand landmarks on the frame for visualization."""
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self._drawing_utils.draw_landmarks(frame, hand_landmarks, mp.solutions.hands.HAND_CONNECTIONS)

    def close(self) -> None:
        """Releases resources used by the detector."""
        self._hands.close()