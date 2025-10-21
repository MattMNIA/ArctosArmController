"""Interactive calibration utility for object centering."""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import cv2

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.vision.camera_manager import CameraManager
from core.vision.calibration.object_centering import (
    AxisCalibration,
    DEFAULT_CALIBRATION_PATH,
    ObjectCenteringCalibration,
    load_calibration,
    save_calibration,
)


def _default_config_path() -> Path:
    return ROOT_DIR / "config" / "default.yml"


def create_driver(name: str, *, urdf_path: Optional[Path] = None, pybullet_gui: bool = False):
    normalized = (name or "sim").strip().lower()
    if normalized == "none":
        return None
    if normalized == "sim":
        from core.drivers.sim_driver import SimDriver

        return SimDriver()
    if normalized == "can":
        from core.drivers.can_driver import CanDriver

        return CanDriver()
    if normalized == "pybullet":
        from core.drivers.pybullet_driver import PyBulletDriver

        candidate = urdf_path or (ROOT_DIR / "models" / "urdf" / "arctos_urdf.urdf")
        return PyBulletDriver(str(candidate), gui=pybullet_gui)
    raise ValueError(f"Unsupported driver '{name}'")


@dataclass
class CalibrationSession:
    axis: str
    joint_index: int
    delta_deg: float
    move_duration: float
    settle_time: float
    driver: Optional[Any]
    camera: Any
    frame_size: Optional[Tuple[int, int]] = None
    status_message: str = field(default="Click on the target point to begin calibration.")
    state: str = field(default="awaiting_first")
    first_point: Optional[Tuple[int, int]] = None
    second_point: Optional[Tuple[int, int]] = None
    error: Optional[BaseException] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _move_thread: Optional[threading.Thread] = field(default=None, init=False)

    def handle_click(self, event, x: int, y: int, *_args) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        with self._lock:
            if self.state == "awaiting_first":
                self.first_point = (x, y)
                self.state = "moving"
                self.status_message = "Commanding arm to move..."
                self._start_motion()
            elif self.state == "awaiting_second":
                self.second_point = (x, y)
                self.state = "complete"
                self.status_message = "Sample recorded."

    def _start_motion(self) -> None:
        if self._move_thread and self._move_thread.is_alive():
            return
        self._move_thread = threading.Thread(target=self._perform_motion, daemon=True)
        self._move_thread.start()

    def _perform_motion(self) -> None:
        if self.driver is None:
            with self._lock:
                self.state = "awaiting_second"
                self.status_message = "Move the arm manually, then click the point again."
            return
        try:
            feedback = self.driver.get_feedback()
            joints = list(feedback.get("q", []))
            if not joints or self.joint_index >= len(joints):
                raise RuntimeError("Driver did not return enough joint feedback entries")
            target = joints[:]
            target[self.joint_index] = joints[self.joint_index] + math.radians(self.delta_deg)
            self.driver.send_joint_targets(target, t_s=self.move_duration)
            time.sleep(max(0.0, self.move_duration + self.settle_time))
            with self._lock:
                if self.state != "complete":
                    self.state = "awaiting_second"
                    self.status_message = "Click the same point again to finish."
        except BaseException as exc:  # pragma: no cover - diagnostic path
            with self._lock:
                self.state = "error"
                self.error = exc
                self.status_message = f"Motion failed: {exc}"

    def draw_overlay(self, frame) -> Any:
        message = self.status_message
        cv2.putText(
            frame,
            message,
            (16, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 200, 0) if self.state != "error" else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        if self.first_point:
            cv2.circle(frame, self.first_point, 6, (255, 140, 0), 2)
        if self.second_point:
            cv2.circle(frame, self.second_point, 6, (0, 200, 255), 2)
        instructions = "Press ESC to abort."
        cv2.putText(
            frame,
            instructions,
            (16, frame.shape[0] - 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )
        return frame

    def is_complete(self) -> bool:
        with self._lock:
            return self.state == "complete"

    def has_error(self) -> bool:
        with self._lock:
            return self.state == "error"

    def compute_axis_calibration(self) -> Tuple[AxisCalibration, Dict[str, float]]:
        if self.first_point is None or self.second_point is None:
            raise RuntimeError("Calibration points are incomplete")
        if abs(self.delta_deg) < 1e-6:
            raise ValueError("delta_deg must be non-zero for calibration")
        if not self.frame_size:
            raise RuntimeError("Frame size unknown; capture a frame before computing calibration")
        delta_pixels = (
            self.second_point[0] - self.first_point[0]
            if self.axis == "horizontal"
            else self.second_point[1] - self.first_point[1]
        )
        ratio = delta_pixels / self.delta_deg
        if abs(ratio) < 1e-6:
            raise ValueError("Observed pixel shift is too small; increase delta_deg and retry")
        pixels_per_degree = abs(ratio)
        invert = ratio < 0
        axis_cal = AxisCalibration(
            joint_index=self.joint_index,
            pixels_per_degree=pixels_per_degree,
            invert=invert,
        )
        metadata = {
            f"pixel_delta_{self.axis}": float(delta_pixels),
            f"delta_deg_{self.axis}": float(self.delta_deg),
            f"pixels_per_degree_{self.axis}": float(pixels_per_degree),
            f"invert_{self.axis}": bool(invert),
            "reference_width": int(self.frame_size[0]),
            "reference_height": int(self.frame_size[1]),
        }
        return axis_cal, metadata


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate pixel-to-degree mapping for object centering")
    parser.add_argument("--axis", choices=["horizontal", "vertical"], required=True, help="Axis to calibrate")
    parser.add_argument("--joint-index", type=int, required=True, help="Joint index that affects the chosen axis")
    parser.add_argument("--delta-deg", type=float, default=5.0, help="Joint rotation applied during calibration")
    parser.add_argument("--move-duration", type=float, default=1.5, help="Seconds to allow the joint move to complete")
    parser.add_argument("--settle-time", type=float, default=0.5, help="Extra wait time after the move completes")
    parser.add_argument("--driver", choices=["sim", "can", "pybullet", "none"], default="sim", help="Driver used to move the arm")
    parser.add_argument("--pybullet-gui", action="store_true", help="Enable PyBullet GUI when using the PyBullet driver")
    parser.add_argument("--urdf-path", type=Path, default=None, help="Override URDF path for the PyBullet driver")
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="Camera configuration file")
    parser.add_argument("--output", type=Path, default=DEFAULT_CALIBRATION_PATH, help="Calibration output path")
    parser.add_argument("--window-name", default="Object Centering Calibration", help="Display window title")
    return parser.parse_args(argv)


def run_session(session: CalibrationSession, window_name: str) -> None:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, session.handle_click)
    try:
        while True:
            ret, frame = session.camera.read()
            if not ret:
                time.sleep(0.05)
                continue
            if session.frame_size is None:
                session.frame_size = (int(frame.shape[1]), int(frame.shape[0]))
            display = session.draw_overlay(frame.copy())
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC key
                raise KeyboardInterrupt("Calibration aborted by user")
            if session.has_error():
                raise RuntimeError(session.status_message)
            if session.is_complete():
                break
    finally:
        cv2.setMouseCallback(window_name, lambda *_args: None)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)

    camera_manager = CameraManager(args.config)
    camera = camera_manager.get_camera()

    driver = create_driver(args.driver, urdf_path=args.urdf_path, pybullet_gui=args.pybullet_gui)
    try:
        if driver is not None:
            driver.connect()
            driver.enable()

        session = CalibrationSession(
            axis=args.axis,
            joint_index=args.joint_index,
            delta_deg=args.delta_deg,
            move_duration=args.move_duration,
            settle_time=args.settle_time,
            driver=driver,
            camera=camera,
        )

        run_session(session, args.window_name)
        axis_cal, metadata = session.compute_axis_calibration()

        try:
            calibration = load_calibration(args.output)
        except FileNotFoundError:
            calibration = ObjectCenteringCalibration()

        if args.axis == "horizontal":
            calibration.horizontal = axis_cal
        else:
            calibration.vertical = axis_cal
        calibration.metadata.update(metadata)
        if session.frame_size:
            calibration.reference_width = session.frame_size[0]
            calibration.reference_height = session.frame_size[1]
        calibration.touch_metadata(axis=args.axis)

        path = save_calibration(calibration, args.output)
        print(f"Saved {args.axis} calibration to {path}")
        print(f"Pixels per degree: {axis_cal.pixels_per_degree:.3f} (invert={axis_cal.invert})")
    finally:
        try:
            camera.release()
        except Exception:
            pass
        if driver is not None:
            try:
                driver.disable()
            except Exception:
                pass
        cv2.destroyAllWindows()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    try:
        main()
    except KeyboardInterrupt:
        print("Calibration aborted")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
