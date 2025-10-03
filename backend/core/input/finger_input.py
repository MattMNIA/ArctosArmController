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
        self._drawing_utils = mp.solutions.drawing_utils if show_window else None
        self._window_created = False
        self._fullscreen = fullscreen
        self._allow_fullscreen_toggle = allow_fullscreen_toggle
        self._max_capture_width = 1280
        self._max_capture_height = 1080
        self._capture_resolution_target: Optional[Tuple[int, int]] = None
        self._capture_resolution_failed = False
        self._initialize_capture_resolution()
        self._reference_palm_size: Optional[float] = None
        self._current_touch_threshold = touch_threshold
        self._current_scale = 1.0
        self._threshold_smoothing = 0.4
        self._hand_scale_smoothing = 0.35
        self._min_threshold_scale = 0.6
        self._max_threshold_scale = 1.8

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
        if self._show_window and self._window_created:
            cv2.destroyWindow(self._window_name)
            self._window_created = False

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
            self._ensure_window()
            display_frame = self._prepare_frame_for_display(frame_to_show)
            cv2.imshow(self._window_name, display_frame)
            key = cv2.waitKey(1) & 0xFF
            if self._allow_fullscreen_toggle and key in (ord("f"), ord("F")):
                self._fullscreen = not self._fullscreen
                self._apply_window_mode()

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

    def _ensure_window(self) -> None:
        if not self._show_window:
            return
        if not self._window_created:
            cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
            self._window_created = True
            self._apply_window_mode()

    def _apply_window_mode(self) -> None:
        if not self._window_created:
            return
        mode = cv2.WINDOW_FULLSCREEN if self._fullscreen else cv2.WINDOW_NORMAL
        cv2.setWindowProperty(
            self._window_name,
            cv2.WND_PROP_FULLSCREEN,
            mode,
        )

    def _prepare_frame_for_display(self, frame):
        if not self._window_created:
            return frame
        if not hasattr(cv2, "getWindowImageRect"):
            return frame

        _, _, window_w, window_h = cv2.getWindowImageRect(self._window_name)
        target_w = int(window_w)
        target_h = int(window_h)
        if target_w <= 0 or target_h <= 0:
            return frame

        self._maybe_adjust_capture_resolution(target_w, target_h)

        frame_h, frame_w = frame.shape[:2]
        if frame_w <= 0 or frame_h <= 0:
            return frame

        scale = max(target_w / frame_w, target_h / frame_h)
        if scale <= 0:
            return frame
        new_w = max(int(round(frame_w * scale)), 1)
        new_h = max(int(round(frame_h * scale)), 1)

        if new_w == frame_w and new_h == frame_h:
            return frame

        interpolation = cv2.INTER_LINEAR if scale > 1.0 else cv2.INTER_AREA
        resized = cv2.resize(frame, (new_w, new_h), interpolation=interpolation)

        y_start = max((resized.shape[0] - target_h) // 2, 0)
        x_start = max((resized.shape[1] - target_w) // 2, 0)
        y_end = min(y_start + target_h, resized.shape[0])
        x_end = min(x_start + target_w, resized.shape[1])
        cropped = resized[y_start:y_end, x_start:x_end]

        if cropped.shape[0] == target_h and cropped.shape[1] == target_w:
            return cropped

        pad_y = max(target_h - cropped.shape[0], 0)
        pad_x = max(target_w - cropped.shape[1], 0)
        pad_top = pad_y // 2
        pad_bottom = pad_y - pad_top
        pad_left = pad_x // 2
        pad_right = pad_x - pad_left

        bordered = cv2.copyMakeBorder(
            cropped,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv2.BORDER_CONSTANT,
            value=(0, 0, 0),
        )

        if bordered.shape[0] != target_h or bordered.shape[1] != target_w:
            bordered = cv2.resize(
                bordered,
                (target_w, target_h),
                interpolation=cv2.INTER_LINEAR,
            )

        return bordered

    def _initialize_capture_resolution(self) -> None:
        if not self._capture or not self._capture.isOpened():
            return

        baseline_w, baseline_h = 1280, 720
        current_w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        current_h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        desired_w = min(max(current_w, baseline_w), self._max_capture_width)
        desired_h = min(max(current_h, baseline_h), self._max_capture_height)

        if current_w >= desired_w and current_h >= desired_h:
            self._capture_resolution_target = (current_w, current_h)
            return

        with self._lock:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, desired_w)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, desired_h)

        actual_w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH) or desired_w)
        actual_h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or desired_h)
        self._capture_resolution_target = (actual_w, actual_h)

        if actual_w < desired_w * 0.9 or actual_h < desired_h * 0.9:
            self._capture_resolution_failed = True

    def _maybe_adjust_capture_resolution(self, target_w: int, target_h: int) -> None:
        if self._capture_resolution_failed:
            return
        if target_w <= 0 or target_h <= 0:
            return
        if not self._capture or not self._capture.isOpened():
            return

        desired_w = min(target_w, self._max_capture_width)
        desired_h = min(target_h, self._max_capture_height)
        desired_w = max(desired_w, 1)
        desired_h = max(desired_h, 1)

        current_w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        current_h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if current_w >= desired_w and current_h >= desired_h:
            self._capture_resolution_target = (current_w, current_h)
            return

        if self._capture_resolution_target == (desired_w, desired_h):
            return

        with self._lock:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, desired_w)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, desired_h)

        actual_w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH) or desired_w)
        actual_h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or desired_h)
        self._capture_resolution_target = (actual_w, actual_h)

        if actual_w < desired_w * 0.9 or actual_h < desired_h * 0.9:
            self._capture_resolution_failed = True