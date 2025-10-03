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
        fullscreen: bool = False,
        allow_fullscreen_toggle: bool = True,
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
        self._base_touch_threshold = touch_threshold
        self._scale = scale
        self._last_gestures = cast(Dict[str, Optional[str]], {"Left": None, "Right": None})
        self._lock = threading.Lock()
        self._show_window = show_window
        self._window_name = window_name
        self._allow_fullscreen_toggle = allow_fullscreen_toggle and show_window
        self._reference_palm_size: Optional[float] = None
        self._current_touch_threshold = touch_threshold
        self._current_scale = 1.0
        self._threshold_smoothing = 0.25
        self._hand_scale_smoothing = 0.2
        self._min_threshold_scale = 0.6
        self._max_threshold_scale = 1.8

        if self._show_window:
            cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
            if fullscreen:
                cv2.setWindowProperty(
                    self._window_name,
                    cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_FULLSCREEN,
                )

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
            frame_to_show = frame if self._show_window else None

        gestures: Dict[str, Optional[str]] = {"Left": None, "Right": None}
        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(
                results.multi_hand_landmarks, results.multi_handedness
            ):
                label = handedness.classification[0].label  # 'Left' or 'Right'
                landmarks = hand_landmarks.landmark
                for finger, tip_idx in self.FINGER_TIPS.items():
                    touching = self._fingers_touching(landmarks, 4, tip_idx)
                    if touching:
                        gestures[label] = finger
                    if frame_to_show is not None:
                        self._draw_touch_indicator(frame_to_show, landmarks, finger, tip_idx, touching)
                    if touching:
                        break

        if frame_to_show is not None:
            cv2.imshow(self._window_name, frame_to_show)
            key = cv2.waitKey(1) & 0xFF
            if self._allow_fullscreen_toggle and key in (ord("f"), ord("F")):
                current_flag = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN)
                target_flag = cv2.WINDOW_NORMAL if current_flag >= 0.5 else cv2.WINDOW_FULLSCREEN
                cv2.setWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN, target_flag)

        return gestures

    def _fingers_touching(self, landmarks, idx1: int, idx2: int) -> bool:
        dx = landmarks[idx2].x - landmarks[idx1].x
        dy = landmarks[idx2].y - landmarks[idx1].y
        dynamic_threshold = self._get_dynamic_touch_threshold(landmarks)
        return (dx * dx + dy * dy) ** 0.5 < dynamic_threshold

    def _get_dynamic_touch_threshold(self, landmarks) -> float:
        base_span = self._compute_palm_span(landmarks)
        if base_span <= 0.0:
            return self._base_touch_threshold

        scale = self._update_hand_scale(base_span)
        target = self._base_touch_threshold * scale
        if self._threshold_smoothing <= 0.0:
            self._current_touch_threshold = target
            return target

        alpha = min(max(self._threshold_smoothing, 0.0), 1.0)
        self._current_touch_threshold = (
            (1.0 - alpha) * self._current_touch_threshold + alpha * target
        )
        return self._current_touch_threshold

    def _update_hand_scale(self, base_span: float) -> float:
        if base_span <= 0.0:
            return self._current_scale

        if self._reference_palm_size is None or self._reference_palm_size <= 0.0:
            self._reference_palm_size = base_span
            self._current_scale = 1.0
            return self._current_scale

        target_scale = base_span / self._reference_palm_size
        target_scale = max(self._min_threshold_scale, min(self._max_threshold_scale, target_scale))

        if self._hand_scale_smoothing <= 0.0:
            self._current_scale = target_scale
            return self._current_scale

        alpha = min(max(self._hand_scale_smoothing, 0.0), 1.0)
        self._current_scale = (1.0 - alpha) * self._current_scale + alpha * target_scale
        return self._current_scale

    @staticmethod
    def _compute_palm_span(landmarks) -> float:
        base_idx_a = 5  # Index finger MCP
        base_idx_b = 17  # Pinky MCP
        dx = landmarks[base_idx_b].x - landmarks[base_idx_a].x
        dy = landmarks[base_idx_b].y - landmarks[base_idx_a].y
        return (dx * dx + dy * dy) ** 0.5

    def _draw_touch_indicator(
        self,
        frame,
        landmarks,
        finger_name: str,
        tip_idx: int,
        touching: bool,
    ) -> None:
        h, w, _ = frame.shape
        thumb = landmarks[4]
        finger = landmarks[tip_idx]
        thumb_pt = (int(thumb.x * w), int(thumb.y * h))
        finger_pt = (int(finger.x * w), int(finger.y * h))
        active_color = (0, 255, 0) if finger_name != "pinky" else (0, 200, 255)
        passive_color = (80, 80, 80)
        color = active_color if touching else passive_color
        cv2.circle(frame, thumb_pt, 6, (0, 128, 255), 2)
        cv2.circle(frame, finger_pt, 8, color, 2)
        cv2.line(frame, thumb_pt, finger_pt, color, 2)