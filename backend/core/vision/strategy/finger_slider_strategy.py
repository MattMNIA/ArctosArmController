import math
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union, cast

import cv2

warnings.filterwarnings(
    "ignore",
    message="SymbolDatabase.GetPrototype() is deprecated",
    category=UserWarning,
)

import mediapipe as mp

from ..cameras.local_camera import LocalCamera
from ..detectors.gesture.gesture_recognizer import GestureRecognizer


class FingerSliderStrategy:
    """Encapsulates the pinch-based slider control logic used by FingerSliderInput."""

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
    gesture_update_interval: float = 0.1,
        min_touch_scale: float = 0.3,
        max_touch_scale: float = 2.0,
        min_hand_separation: float = 0.12,
    ) -> None:
        self._camera = LocalCamera(camera_index)
        self._camera_index = self._camera.camera_index
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=max_num_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )
        self._touch_threshold = touch_threshold
        self._base_touch_threshold = touch_threshold
        self._joint_pairs = joint_pairs or self.DEFAULT_JOINT_PAIRS
        self._horizontal_gain = horizontal_gain
        self._vertical_gain = vertical_gain
        self._deadzone = max(0.0, deadzone)
        self._base_deadzone = self._deadzone
        self._current_deadzone = self._deadzone
        self._update_threshold = max(0.0, update_threshold)
        self._base_update_threshold = self._update_threshold
        self._current_update_threshold = self._update_threshold
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
        self._allow_fullscreen_toggle = allow_fullscreen_toggle and show_window
        self._drawing_utils = mp.solutions.drawing_utils
        self._hand_overlay_enabled = False
        self._reference_palm_size: Optional[float] = None
        self._current_touch_threshold = touch_threshold
        self._current_scale = 1.0
        self._threshold_smoothing = 0.25
        self._hand_scale_smoothing = 0.2
        self._min_threshold_scale = max(0.1, min_touch_scale)
        self._max_threshold_scale = max(self._min_threshold_scale, max_touch_scale)
        self._gesture_recognizer = (
            GestureRecognizer(gesture_config_path) if enable_gestures else None
        )
        self._pending_gesture_events: List[Tuple[str, Union[int, str], float]] = []
        self._gesture_update_interval = max(0.0, gesture_update_interval)
        self._last_gesture_update = 0.0
        self._last_gesture_overlays: List[str] = []
        self._status_message: str = ""
        self._status_message_until: float = 0.0
        self._reference_update_interval = 1.0
        self._reference_update_alpha = 0.35
        self._last_reference_update = 0.0
        self._min_hand_separation = max(0.0, min_hand_separation)

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
            if self._gesture_recognizer is not None:
                self._update_gesture_recognizer(None, None, [])
            events.extend(self._consume_gesture_events())
            return events

        for joint in self._joint_indices:
            current = joint_values.get(joint, 0.0)
            previous = self._joint_state.get(joint, 0.0)

            if abs(current) < self._current_deadzone:
                current = 0.0

            if current == 0.0 and previous != 0.0:
                events.append(("release", joint, 0.0))
            elif current != 0.0:
                if previous == 0.0 or abs(current - previous) >= self._current_update_threshold:
                    events.append(("press", joint, current))

            self._joint_state[joint] = current

        current_gripper = self._latest_gripper_value
        if abs(current_gripper) < self._current_deadzone:
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
                or abs(current_gripper - previous_gripper) >= self._current_update_threshold
            ):
                events.append(("press", f"gripper_{curr_dir}", abs(current_gripper)))

        self._joint_state["gripper"] = current_gripper

        events.extend(self._consume_gesture_events())

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

    def _process_frame(self) -> Optional[Dict[int, float]]:
        with self._lock:
            if not self._camera or not self._camera.is_opened():
                return None

            ret, frame = self._camera.read()
            if not ret:
                return None

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
            frame_to_show = frame if self._show_window else None
        joint_values: Dict[int, float] = {idx: 0.0 for idx in self._joint_indices}
        prev_joint_values = dict(self._joint_state)
        gripper_value = 0.0
        active_keys: Set[Tuple[str, str]] = set()
        overlay_rows: List[str] = []

        filtered_landmarks: Optional[List[Any]] = None
        filtered_handedness: Optional[List[Any]] = None

        if results.multi_hand_landmarks and results.multi_handedness:
            filtered_landmarks, filtered_handedness = self._filter_overlapping_hands(
                list(results.multi_hand_landmarks),
                list(results.multi_handedness),
            )

        if filtered_landmarks and filtered_handedness:
            for hand_landmarks, handedness in zip(filtered_landmarks, filtered_handedness):
                label = handedness.classification[0].label  # 'Left' or 'Right'
                landmarks = hand_landmarks.landmark
                thumb_tip = landmarks[4]
                if frame_to_show is not None and self._hand_overlay_enabled:
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
                        continue

        for key in list(self._pinch_states.keys()):
            if key not in active_keys:
                del self._pinch_states[key]

        self._update_gesture_recognizer(filtered_landmarks, filtered_handedness, overlay_rows)

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
            overlay_start_y = 40
            if self._status_message and time.time() < self._status_message_until:
                cv2.putText(
                    frame_to_show,
                    self._status_message,
                    (10, overlay_start_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 200, 255),
                    1,
                    cv2.LINE_AA,
                )
                overlay_start_y += 20
            elif self._status_message:
                self._status_message = ""
            for idx, text in enumerate(overlay_rows):
                cv2.putText(
                    frame_to_show,
                    text,
                    (10, overlay_start_y + idx * 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
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
            if key in (ord("r"), ord("R")):
                self._reference_palm_size = None
                self._current_scale = 1.0
                self._current_touch_threshold = self._base_touch_threshold
                self._current_deadzone = self._base_deadzone
                self._current_update_threshold = self._base_update_threshold
                self._last_reference_update = 0.0
                self._status_message = "Recalibrated palm reference"
                self._status_message_until = time.time() + 2.0
                self._pinch_states.clear()

        self._latest_joint_values = dict(joint_values)
        self._latest_gripper_value = gripper_value
        return joint_values

    def _consume_gesture_events(self) -> List[Tuple[str, Union[int, str], float]]:
        if not self._pending_gesture_events:
            return []
        events = list(self._pending_gesture_events)
        self._pending_gesture_events = []
        return events

    def _update_gesture_recognizer(
        self,
        multi_hand_landmarks: Optional[Sequence[object]],
        multi_handedness: Optional[Sequence[object]],
        overlay_rows: List[str],
    ) -> None:
        if self._gesture_recognizer is None:
            self._pending_gesture_events = []
            self._last_gesture_overlays = []
            return

        now = time.time()
        if (
            self._gesture_update_interval > 0.0
            and now - self._last_gesture_update < self._gesture_update_interval
        ):
            overlay_rows.extend(self._last_gesture_overlays)
            return

        events, overlays = self._gesture_recognizer.process(multi_hand_landmarks, multi_handedness)
        self._pending_gesture_events = []
        for event in events:
            if event.change == "start":
                self._pending_gesture_events.append(
                    ("press", event.event, max(event.confidence, 0.0))
                )
            elif event.change == "end":
                self._pending_gesture_events.append(("release", event.event, 0.0))
        overlay_rows.extend(overlays)
        self._last_gesture_overlays = list(overlays)
        self._last_gesture_update = now

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
        return 0.0 if abs(value) < self._current_deadzone else value

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, value))

    def _fingers_touching(self, landmarks, idx1: int, idx2: int) -> bool:
        dx = landmarks[idx2].x - landmarks[idx1].x
        dy = landmarks[idx2].y - landmarks[idx1].y
        dynamic_threshold = self._get_dynamic_touch_threshold(landmarks)
        return (dx * dx + dy * dy) ** 0.5 < dynamic_threshold

    def _get_dynamic_touch_threshold(self, landmarks) -> float:
        base_span = self._compute_reference_span(landmarks)
        if base_span <= 0.0:
            return self._base_touch_threshold

        scale = self._update_hand_scale(base_span)
        self._apply_dynamic_threshold_scaling(scale)
        target = self._base_touch_threshold * scale
        if self._threshold_smoothing <= 0.0:
            self._current_touch_threshold = target
            return target

        alpha = min(max(self._threshold_smoothing, 0.0), 1.0)
        self._current_touch_threshold = (
            (1.0 - alpha) * self._current_touch_threshold + alpha * target
        )
        return self._current_touch_threshold

    def _maybe_update_reference(self, base_span: float) -> None:
        if base_span <= 0.0:
            return

        now = time.time()
        if self._reference_palm_size is None or self._reference_palm_size <= 0.0:
            self._reference_palm_size = base_span
            self._last_reference_update = now
            return

        if now - self._last_reference_update < self._reference_update_interval:
            return

        alpha = min(max(self._reference_update_alpha, 0.0), 1.0)
        self._reference_palm_size = (
            (1.0 - alpha) * self._reference_palm_size + alpha * base_span
        )
        self._last_reference_update = now

    def _update_hand_scale(self, base_span: float) -> float:
        if base_span <= 0.0:
            return self._current_scale

        self._maybe_update_reference(base_span)

        if self._reference_palm_size is None or self._reference_palm_size <= 0.0:
            self._reference_palm_size = base_span
            self._last_reference_update = time.time()
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

    def _apply_dynamic_threshold_scaling(self, scale: float) -> None:
        target_deadzone = max(0.0, self._base_deadzone * scale)
        target_update_threshold = max(0.0, self._base_update_threshold * scale)

        if self._threshold_smoothing <= 0.0:
            self._current_deadzone = target_deadzone
            self._current_update_threshold = target_update_threshold
            return

        alpha = min(max(self._threshold_smoothing, 0.0), 1.0)
        self._current_deadzone = (
            (1.0 - alpha) * self._current_deadzone + alpha * target_deadzone
        )
        self._current_update_threshold = (
            (1.0 - alpha) * self._current_update_threshold + alpha * target_update_threshold
        )

    def _filter_overlapping_hands(
        self,
        hand_landmarks_list: Sequence[Any],
        handedness_list: Sequence[Any],
    ) -> Tuple[List[Any], List[Any]]:
        if not hand_landmarks_list or not handedness_list or self._min_hand_separation <= 0.0:
            return list(hand_landmarks_list), list(handedness_list)

        filtered: List[Dict[str, Any]] = []

        for landmarks_obj, handedness_obj in zip(hand_landmarks_list, handedness_list):
            if not hasattr(landmarks_obj, "landmark") or not landmarks_obj.landmark:
                continue
            wrist = landmarks_obj.landmark[0]
            score = 0.0
            try:
                if handedness_obj.classification:
                    score = handedness_obj.classification[0].score
            except AttributeError:
                score = 0.0

            keep = True
            for idx, entry in enumerate(filtered):
                other_wrist = entry["landmarks"].landmark[0]
                separation = math.hypot(wrist.x - other_wrist.x, wrist.y - other_wrist.y)
                if separation < self._min_hand_separation:
                    if score > entry["score"]:
                        filtered[idx] = {
                            "landmarks": landmarks_obj,
                            "handedness": handedness_obj,
                            "score": score,
                        }
                    keep = False
                    break

            if keep:
                filtered.append(
                    {
                        "landmarks": landmarks_obj,
                        "handedness": handedness_obj,
                        "score": score,
                    }
                )

        return (
            [entry["landmarks"] for entry in filtered],
            [entry["handedness"] for entry in filtered],
        )

    @staticmethod
    def _compute_reference_span(landmarks) -> float:
        wrist = landmarks[0]
        mcp_indices = (5, 9, 13, 17)
        distances: List[float] = []
        wx, wy = wrist.x, wrist.y
        for idx in mcp_indices:
            pt = landmarks[idx]
            dx = pt.x - wx
            dy = pt.y - wy
            distances.append((dx * dx + dy * dy) ** 0.5)
        if not distances:
            return 0.0
        return sum(distances) / len(distances)

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
        return f"Pinky Gripper: {vertical:+.2f}"

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