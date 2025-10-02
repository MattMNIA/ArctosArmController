import cv2
import mediapipe as mp
import threading
from typing import Dict, List, Tuple, Union, Any, Optional, cast

from .base_input import InputController
from .camera_selector import select_camera_index


class FingerInput(InputController):
    """MediaPipe-powered input that maps thumb–finger touches to joint commands."""

    FINGER_TIPS = {
        "index": 8,
        "middle": 12,
        "ring": 16,
        "pinky": 20,
    }

    DEFAULT_JOINT_MAP = {
        "index": 0,
        "middle": 1,
        "ring": 2,
        "pinky": 3,
    }

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
    ) -> None:
        selected_index = select_camera_index(camera_index)
        self._camera_index = selected_index
        self._capture = cv2.VideoCapture(selected_index, cv2.CAP_DSHOW)
        if not self._capture or not self._capture.isOpened():
            raise RuntimeError(f"Failed to open camera index {selected_index}.")
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._joint_map = joint_map or self.DEFAULT_JOINT_MAP
        self._touch_threshold = touch_threshold
        self._scale = scale
        self._last_gestures = cast(Dict[str, Optional[str]], {"Left": None, "Right": None})
        self._lock = threading.Lock()
        self._show_window = show_window
        self._window_name = window_name
        self._drawing_utils = mp.solutions.drawing_utils if show_window else None

    def get_commands(self) -> Dict[Union[int, str], float]:
        self._process_frame()
        return {}

    def get_events(self) -> List[Tuple[str, Any, float]]:
        gestures = self._process_frame()
        events: List[Tuple[str, Any, float]] = []
        if gestures is None:
            return events

        for hand in ("Left", "Right"):
            current = gestures[hand]
            previous = self._last_gestures[hand]
            if current == previous:
                continue

            if previous is not None:
                joint_idx = self._joint_map.get(previous)
                if joint_idx is not None:
                    events.append(("release", joint_idx, 0.0))

            if current is not None:
                joint_idx = self._joint_map.get(current)
                if joint_idx is not None:
                    direction = 1.0 if hand == "Right" else -1.0
                    events.append(("press", joint_idx, direction * self._scale))

            self._last_gestures[hand] = current

        return events

    def close(self) -> None:
        with self._lock:
            if self._hands:
                self._hands.close()
            if self._capture and self._capture.isOpened():
                self._capture.release()
        if self._show_window:
            cv2.destroyWindow(self._window_name)

    def __del__(self) -> None:
        self.close()

    def _process_frame(self) -> Optional[Dict[str, Optional[str]]]:
        with self._lock:
            if not self._capture or not self._capture.isOpened():
                return None

            ret, frame = self._capture.read()
            if not ret:
                return {"Left": None, "Right": None}

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
            frame_to_show = frame.copy() if self._show_window else None

        gestures: Dict[str, Optional[str]] = {"Left": None, "Right": None}
        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(
                results.multi_hand_landmarks, results.multi_handedness
            ):
                label = handedness.classification[0].label  # 'Left' or 'Right'
                landmarks = hand_landmarks.landmark
                for finger, tip_idx in self.FINGER_TIPS.items():
                    if self._fingers_touching(landmarks, 4, tip_idx):
                        gestures[label] = finger
                        break

                if frame_to_show is not None and self._drawing_utils is not None:
                    self._drawing_utils.draw_landmarks(
                        frame_to_show,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                    )

        if frame_to_show is not None:
            cv2.imshow(self._window_name, frame_to_show)
            cv2.waitKey(1)

        return gestures

    def _fingers_touching(self, landmarks, idx1: int, idx2: int) -> bool:
        dx = landmarks[idx2].x - landmarks[idx1].x
        dy = landmarks[idx2].y - landmarks[idx1].y
        return (dx * dx + dy * dy) ** 0.5 < self._touch_threshold