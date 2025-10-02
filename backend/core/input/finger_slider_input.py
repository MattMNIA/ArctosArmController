import threading
from typing import Any, Dict, List, Optional, Tuple, Union, Set, cast

import cv2
import mediapipe as mp

from .base_input import InputController
from .camera_selector import select_camera_index


class FingerSliderInput(InputController):
    """Continuous teleoperation input that maps thumb–finger pinches to two-axis sliders.

    Touching the thumb to the index finger controls joints 0 (horizontal) and 1 (vertical).
    Touching the thumb to the middle finger controls joints 2 and 3.
    Touching the thumb to the ring finger controls joints 4 and 5.
    Touching the thumb to the pinky finger controls the gripper (vertical only).

    Moving the pinched finger left/right or up/down modulates the velocity sent to
    each joint, enabling smooth, proportional control without repeatedly tapping.
    """

    FINGER_TIPS = {
        "index": 8,
        "middle": 12,
        "ring": 16,
        "pinky": 20,
    }

    DEFAULT_JOINT_PAIRS: Dict[str, Tuple[int, int]] = {
        "index": (0, 1),
        "middle": (3, 2),
        "ring": (5, 4),
    }

    INVERTED_VERTICAL_JOINTS = {2}
    INVERTED_HORIZONTAL_JOINTS = {3, 5}

    def __init__(
        self,
        camera_index: Optional[int] = None,
        touch_threshold: float = 0.1,
        joint_pairs: Optional[Dict[str, Tuple[int, int]]] = None,
        max_num_hands: int = 2,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.7,
        horizontal_gain: float = 2.0,
        vertical_gain: float = 2.0,
        deadzone: float = 0.1,
        update_threshold: float = 0.03,
        smoothing: float = 0.3,
        invert_left_horizontal: bool = True,
        show_window: bool = True,
        window_name: str = "Finger Slider Input",
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
        self._touch_threshold = touch_threshold
        self._joint_pairs = joint_pairs or self.DEFAULT_JOINT_PAIRS
        self._horizontal_gain = horizontal_gain
        self._vertical_gain = vertical_gain
        self._deadzone = max(0.0, deadzone)
        self._update_threshold = max(0.0, update_threshold)
        self._smoothing = min(max(smoothing, 0.0), 1.0)
        self._invert_left_horizontal = invert_left_horizontal

        self._lock = threading.Lock()
        self._pinch_states: Dict[Tuple[str, str], Dict[str, float]] = {}
        self._joint_indices = sorted(
            {idx for pair in self._joint_pairs.values() for idx in pair}
        )
        self._joint_state: Dict[Union[int, str], float] = {
            idx: 0.0 for idx in self._joint_indices
        }
        self._joint_state["gripper"] = 0.0
        self._latest_joint_values: Dict[int, float] = {
            idx: 0.0 for idx in self._joint_indices
        }
        self._latest_gripper_value = 0.0

        self._show_window = show_window
        self._window_name = window_name
        self._drawing_utils = mp.solutions.drawing_utils if show_window else None
        self._window_created = False
        self._fullscreen = fullscreen
        self._allow_fullscreen_toggle = allow_fullscreen_toggle
        self._max_capture_width = 1920
        self._max_capture_height = 1080
        self._capture_resolution_target: Optional[Tuple[int, int]] = None
        self._capture_resolution_failed = False
        self._initialize_capture_resolution()

    def get_commands(self) -> Dict[Union[int, str], float]:
        commands = cast(
            Dict[Union[int, str], float], dict(self._latest_joint_values)
        )
        commands["gripper"] = self._latest_gripper_value
        return commands

    def get_events(self) -> List[Tuple[str, Any, float]]:
        joint_values = self._process_frame()
        events: List[Tuple[str, Any, float]] = []

        if joint_values is None:
            for joint, previous in self._joint_state.items():
                if joint == "gripper":
                    continue
                if previous != 0.0:
                    events.append(("release", joint, 0.0))
                    self._joint_state[joint] = 0.0
            previous_gripper = self._joint_state.get("gripper", 0.0)
            if previous_gripper != 0.0:
                events.append(
                    (
                        "release",
                        "gripper_open" if previous_gripper > 0 else "gripper_close",
                        0.0,
                    )
                )
                self._joint_state["gripper"] = 0.0
            self._latest_gripper_value = 0.0
            return events

        for joint in self._joint_indices:
            current = joint_values.get(joint, 0.0)
            previous = self._joint_state.get(joint, 0.0)

            if abs(current) < self._deadzone:
                current = 0.0

            if current == 0.0 and previous != 0.0:
                events.append(("release", joint, 0.0))
            elif current != 0.0:
                if previous == 0.0 or abs(current - previous) >= self._update_threshold:
                    events.append(("press", joint, current))

            self._joint_state[joint] = current

        current_gripper = self._latest_gripper_value
        if abs(current_gripper) < self._deadzone:
            current_gripper = 0.0
        previous_gripper = self._joint_state.get("gripper", 0.0)
        prev_dir = (
            "open" if previous_gripper > 0 else "close" if previous_gripper < 0 else None
        )
        curr_dir = "open" if current_gripper > 0 else "close" if current_gripper < 0 else None

        if prev_dir and (curr_dir != prev_dir or curr_dir is None):
            events.append(("release", f"gripper_{prev_dir}", 0.0))

        if curr_dir:
            if (
                prev_dir != curr_dir
                or abs(current_gripper - previous_gripper) >= self._update_threshold
            ):
                events.append(("press", f"gripper_{curr_dir}", abs(current_gripper)))

        self._joint_state["gripper"] = current_gripper

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

    def _process_frame(self) -> Optional[Dict[int, float]]:
        with self._lock:
            if not self._capture or not self._capture.isOpened():
                return None

            ret, frame = self._capture.read()
            if not ret:
                return None

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
            frame_to_show = frame.copy() if self._show_window else None
        joint_values: Dict[int, float] = {idx: 0.0 for idx in self._joint_indices}
        prev_joint_values = dict(self._joint_state)
        gripper_value = 0.0
        active_keys: Set[Tuple[str, str]] = set()
        overlay_rows: List[str] = []

        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(
                results.multi_hand_landmarks, results.multi_handedness
            ):
                label = handedness.classification[0].label  # 'Left' or 'Right'
                landmarks = hand_landmarks.landmark
                thumb_tip = landmarks[4]

                if frame_to_show is not None and self._drawing_utils is not None:
                    self._drawing_utils.draw_landmarks(
                        frame_to_show,
                        hand_landmarks,
                        mp.solutions.hands.HAND_CONNECTIONS,
                    )

                for finger_name, tip_idx in self.FINGER_TIPS.items():
                    if finger_name not in self._joint_pairs and finger_name != "pinky":
                        continue

                    key = (label, finger_name)
                    finger_tip = landmarks[tip_idx]

                    if self._fingers_touching(landmarks, 4, tip_idx):
                        active_keys.add(key)
                        state = self._pinch_states.setdefault(
                            key,
                            {"base_x": finger_tip.x, "base_y": finger_tip.y},
                        )

                        if finger_name == "pinky":
                            raw_vertical = self._clamp(
                                (state["base_y"] - finger_tip.y) * self._vertical_gain
                            )
                            raw_vertical = self._apply_deadzone(raw_vertical)

                            previous = prev_joint_values.get("gripper", 0.0)
                            if self._smoothing > 0.0:
                                vertical = previous + self._smoothing * (
                                    raw_vertical - previous
                                )
                            else:
                                vertical = raw_vertical

                            vertical = self._apply_deadzone(self._clamp(vertical))
                            gripper_value = vertical

                            if frame_to_show is not None:
                                overlay_rows.append(
                                    self._draw_gripper_overlay(
                                        frame_to_show,
                                        thumb_tip,
                                        finger_tip,
                                        state,
                                        vertical,
                                    )
                                )
                            continue

                        raw_horizontal = self._clamp(
                            (finger_tip.x - state["base_x"]) * self._horizontal_gain
                        )
                        raw_vertical = self._clamp(
                            (state["base_y"] - finger_tip.y) * self._vertical_gain
                        )

                        joint_horizontal, joint_vertical = self._joint_pairs[finger_name]

                        if self._invert_left_horizontal and label == "Left":
                            raw_horizontal *= -1.0

                        if joint_horizontal in self.INVERTED_HORIZONTAL_JOINTS:
                            raw_horizontal *= -1.0

                        raw_horizontal = self._apply_deadzone(raw_horizontal)
                        raw_vertical = self._apply_deadzone(raw_vertical)
                        if joint_vertical in self.INVERTED_VERTICAL_JOINTS:
                            raw_vertical *= -1.0
                        horizontal = self._apply_smoothing(
                            joint_horizontal, raw_horizontal, prev_joint_values
                        )
                        vertical = self._apply_smoothing(
                            joint_vertical, raw_vertical, prev_joint_values
                        )

                        horizontal = self._apply_deadzone(horizontal)
                        vertical = self._apply_deadzone(vertical)

                        joint_values[joint_horizontal] = horizontal
                        joint_values[joint_vertical] = vertical

                        if frame_to_show is not None:
                            overlay_rows.append(
                                self._draw_slider_overlay(
                                    frame_to_show,
                                    thumb_tip,
                                    finger_tip,
                                    state,
                                    finger_name,
                                    joint_horizontal,
                                    joint_vertical,
                                    horizontal,
                                    vertical,
                                )
                            )
                    else:
                        # If the pinch is broken, we'll release the joint values later.
                        continue

        for key in list(self._pinch_states.keys()):
            if key not in active_keys:
                del self._pinch_states[key]

        if frame_to_show is not None:
            for idx, text in enumerate(overlay_rows):
                cv2.putText(
                    frame_to_show,
                    text,
                    (10, 20 + idx * 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            self._ensure_window()
            display_frame = self._prepare_frame_for_display(frame_to_show)
            cv2.imshow(self._window_name, display_frame)
            key = cv2.waitKey(1) & 0xFF
            if self._allow_fullscreen_toggle and key in (ord("f"), ord("F")):
                self._fullscreen = not self._fullscreen
                self._apply_window_mode()

        self._latest_joint_values = dict(joint_values)
        self._latest_gripper_value = gripper_value
        return joint_values

    def _apply_smoothing(
        self, joint_index: Union[int, str], target: float, prev_values: Dict[Union[int, str], float]
    ) -> float:
        target = self._clamp(target)
        if self._smoothing <= 0.0:
            return target
        previous = prev_values.get(joint_index, 0.0)
        smoothed = previous + self._smoothing * (target - previous)
        return self._clamp(smoothed)

    def _apply_deadzone(self, value: float) -> float:
        return 0.0 if abs(value) < self._deadzone else value

    def _clamp(self, value: float) -> float:
        return max(-1.0, min(1.0, value))

    def _fingers_touching(self, landmarks, idx1: int, idx2: int) -> bool:
        dx = landmarks[idx2].x - landmarks[idx1].x
        dy = landmarks[idx2].y - landmarks[idx1].y
        return (dx * dx + dy * dy) ** 0.5 < self._touch_threshold

    def _draw_slider_overlay(
        self,
        frame,
        thumb_tip,
        finger_tip,
        state: Dict[str, float],
        finger_name: str,
        joint_horizontal: int,
        joint_vertical: int,
        horizontal: float,
        vertical: float,
    ) -> str:
        h, w, _ = frame.shape

        def to_pixel(x: float, y: float) -> Tuple[int, int]:
            px = int(max(0.0, min(1.0, x)) * w)
            py = int(max(0.0, min(1.0, y)) * h)
            return px, py

        base_pt = to_pixel(state["base_x"], state["base_y"])
        finger_pt = to_pixel(finger_tip.x, finger_tip.y)
        thumb_pt = to_pixel(thumb_tip.x, thumb_tip.y)

        cv2.circle(frame, finger_pt, 8, (0, 255, 0), 2)
        cv2.circle(frame, thumb_pt, 6, (0, 128, 255), 2)
        cv2.circle(frame, base_pt, 5, (255, 0, 0), 2)
        cv2.line(frame, base_pt, (finger_pt[0], base_pt[1]), (200, 200, 0), 1)
        cv2.line(frame, base_pt, (base_pt[0], finger_pt[1]), (200, 0, 200), 1)
        cv2.line(frame, thumb_pt, finger_pt, (0, 255, 255), 1)

        return (
            f"{finger_name.capitalize()} H[{joint_horizontal}]: {horizontal:+.2f} "
            f"V[{joint_vertical}]: {vertical:+.2f}"
        )

    def _draw_gripper_overlay(
        self,
        frame,
        thumb_tip,
        finger_tip,
        state: Dict[str, float],
        vertical: float,
    ) -> str:
        h, w, _ = frame.shape

        def to_pixel(x: float, y: float) -> Tuple[int, int]:
            px = int(max(0.0, min(1.0, x)) * w)
            py = int(max(0.0, min(1.0, y)) * h)
            return px, py

        base_pt = to_pixel(state["base_x"], state["base_y"])
        finger_pt = to_pixel(finger_tip.x, finger_tip.y)
        thumb_pt = to_pixel(thumb_tip.x, thumb_tip.y)

        cv2.circle(frame, finger_pt, 8, (0, 200, 0), 2)
        cv2.circle(frame, thumb_pt, 6, (0, 128, 255), 2)
        cv2.circle(frame, base_pt, 5, (255, 0, 0), 2)
        cv2.line(frame, thumb_pt, finger_pt, (0, 255, 255), 1)

        return f"Pinky Gripper: {vertical:+.2f}"

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
