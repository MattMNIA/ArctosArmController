import threading
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import cv2
import mediapipe as mp

from ..cameras.local_camera import LocalCamera


class FingerTouchStrategy:
    """Encapsulates the finger touch detection pipeline used by FingerInput."""

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
    DEFAULT_REFERENCE_SPAN: float = 0.2

    def __init__(
        self,
        camera_index: Optional[int] = None,
        touch_threshold: float = 0.05,
        touch_ratio: Optional[float] = None,
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
        self._camera = LocalCamera(camera_index)
        self._camera_index = self._camera.camera_index
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._joint_map = joint_map or self.DEFAULT_JOINT_MAP
        self._touch_threshold = touch_threshold
        self._touch_ratio = touch_ratio if touch_ratio is not None else (
            touch_threshold / self.DEFAULT_REFERENCE_SPAN
        )
        self._touch_ratio = max(1e-6, float(self._touch_ratio))
        self._base_touch_threshold = self._touch_ratio * self.DEFAULT_REFERENCE_SPAN
        self._scale = scale
        self._last_gestures = cast(Dict[str, Optional[str]], {"Left": None, "Right": None})
        self._lock = threading.Lock()
        self._show_window = show_window
        self._window_name = window_name
        self._allow_fullscreen_toggle = allow_fullscreen_toggle and show_window
        self._drawing_utils = mp.solutions.drawing_utils
        self._hand_overlay_enabled = False
        self._current_touch_threshold = self._base_touch_threshold
        self._current_hand_span = self.DEFAULT_REFERENCE_SPAN
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

    @property
    def camera_index(self) -> int:
        return self._camera_index

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
            if self._camera and self._camera.is_opened():
                self._camera.release()
        if self._show_window:
            cv2.destroyWindow(self._window_name)

    def __del__(self) -> None:
        self.close()

    # Internal helpers -------------------------------------------------

    def _process_frame(self) -> Optional[Dict[str, Optional[str]]]:
        with self._lock:
            if not self._camera or not self._camera.is_opened():
                return None

            ret, frame = self._camera.read()
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
                thumb_tip = landmarks[4]
                dynamic_threshold = self._get_dynamic_touch_threshold(landmarks)
                if frame_to_show is not None:
                    self._draw_touch_threshold_circle(frame_to_show, thumb_tip, dynamic_threshold)
                if frame_to_show is not None and self._hand_overlay_enabled:
                    self._drawing_utils.draw_landmarks(
                        frame_to_show,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                    )
                for finger, tip_idx in self.FINGER_TIPS.items():
                    touching = self._fingers_touching(
                        landmarks, 4, tip_idx, dynamic_threshold
                    )
                    if touching:
                        gestures[label] = finger
                    if frame_to_show is not None:
                        self._draw_touch_indicator(frame_to_show, landmarks, finger, tip_idx, touching)
                    if touching:
                        break

        if frame_to_show is not None:
            status_text = f"Overlay [H]: {'ON' if self._hand_overlay_enabled else 'OFF'}"
            status_color = (0, 200, 0) if self._hand_overlay_enabled else (160, 160, 160)
            cv2.putText(
                frame_to_show,
                status_text,
                (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                status_color,
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(self._window_name, frame_to_show)
            key = cv2.waitKey(1) & 0xFF
            if self._allow_fullscreen_toggle and key in (ord("f"), ord("F")):
                current_flag = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN)
                target_flag = cv2.WINDOW_NORMAL if current_flag >= 0.5 else cv2.WINDOW_FULLSCREEN
                cv2.setWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN, target_flag)
            if key in (ord("h"), ord("H")):
                self._hand_overlay_enabled = not self._hand_overlay_enabled

        return gestures

    def _fingers_touching(
        self,
        landmarks,
        idx1: int,
        idx2: int,
        dynamic_threshold: Optional[float] = None,
    ) -> bool:
        dx = landmarks[idx2].x - landmarks[idx1].x
        dy = landmarks[idx2].y - landmarks[idx1].y
        if dynamic_threshold is None:
            dynamic_threshold = self._get_dynamic_touch_threshold(landmarks)
        return (dx * dx + dy * dy) ** 0.5 < dynamic_threshold

    def _get_dynamic_touch_threshold(self, landmarks) -> float:
        base_span = self._compute_palm_span(landmarks)
        if base_span <= 0.0:
            return self._current_touch_threshold

        span = self._update_hand_span(base_span)
        unclamped_threshold = self._touch_ratio * span
        min_threshold = self._base_touch_threshold * self._min_threshold_scale
        max_threshold = self._base_touch_threshold * self._max_threshold_scale
        target = max(min_threshold, min(max_threshold, unclamped_threshold))

        if self._threshold_smoothing <= 0.0:
            self._current_touch_threshold = target
        else:
            alpha = min(max(self._threshold_smoothing, 0.0), 1.0)
            self._current_touch_threshold = (
                (1.0 - alpha) * self._current_touch_threshold + alpha * target
            )
        return self._current_touch_threshold

    def _update_hand_span(self, base_span: float) -> float:
        if base_span <= 0.0:
            return self._current_hand_span

        if self._hand_scale_smoothing <= 0.0:
            self._current_hand_span = base_span
            return self._current_hand_span

        alpha = min(max(self._hand_scale_smoothing, 0.0), 1.0)
        self._current_hand_span = (
            (1.0 - alpha) * self._current_hand_span + alpha * base_span
        )
        return self._current_hand_span

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

    def _draw_touch_threshold_circle(self, frame, thumb_tip, threshold: float) -> None:
        if threshold <= 0.0:
            return

        h, w, _ = frame.shape
        cx = int(max(0.0, min(1.0, thumb_tip.x)) * w)
        cy = int(max(0.0, min(1.0, thumb_tip.y)) * h)
        avg_extent = 0.5 * (w + h)
        radius = int(max(2.0, min(threshold * avg_extent, float(max(w, h)))))
        cv2.circle(frame, (cx, cy), radius, (255, 200, 0), 1, lineType=cv2.LINE_AA)