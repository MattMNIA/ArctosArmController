"""Utility script to capture Charuco calibration frames with teleoperation control.

This module wires together the CAN-based motion service, the teleoperation
controller driven by the finger slider input strategy, and the ESP32-based IP
camera to facilitate manual capture of calibration images alongside robot joint
positions.

Usage (from repository root)::

	python -m core.vision.calibration.capture_calibration_data --camera-url http://<ip>/stream

The script will launch the motion service (CAN driver), start teleoperation so
the operator can position the arm with the finger slider UI, and wait for
keyboard commands to snapshot frames. When the user presses ``c`` (followed by
Enter), the script will grab a still image from the IP camera, query the current
joint state, and persist both the PNG image and structured metadata under the
``calibration_data`` directory.

The resulting ``metadata.json`` has the form::

	{
	  "board": {
		"type": "charuco",
		"square_size_mm": 36.3,
		"grid": {"rows": 5, "cols": 7}
	  },
	  "frames": [
		{
		  "timestamp": "2025-10-12T18:23:45.123456Z",
		  "image": "images/frame_000.png",
		  "joint_positions": [0.1, -1.2, 0.5, 0.3, -0.2, 1.0]
		}
	  ]
	}

The additional fields provide downstream calibration tooling with context about
the Charuco board specifications supplied by the operator.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import cv2
import numpy as np

from ...motion_service import MotionService
from ...teleop_controller import TeleopController
from ...drivers.can_driver import CanDriver
from ...vision.cameras.ip_camera import IPCamera
from ...input.finger_slider_input import FingerSliderInput
from ...input.xbox_input import XboxController
from ...input.keyboard_input import KeyboardController
from ...input.finger_input import FingerInput
from queue import Queue, Empty
import platform
try:
	import msvcrt
except Exception:
	msvcrt = None


LOGGER = logging.getLogger(__name__)


def _default_output_root() -> Path:
	return Path(__file__).resolve().parent / "calibration_data"


@dataclass
class BoardMetadata:
	"""Static description of the Charuco board used for calibration."""

	square_size_mm: float = 36.3
	grid_rows: int = 5
	grid_cols: int = 7
	pattern: str = "charuco"

	def as_dict(self) -> Dict[str, object]:
		return {
			"type": self.pattern,
			"square_size_mm": self.square_size_mm,
			"grid": {"rows": self.grid_rows, "cols": self.grid_cols},
		}


@dataclass
class CalibrationMetadata:
	"""Manages metadata persistence for captured calibration frames."""

	path: Path
	board: BoardMetadata
	data: Dict[str, object] = field(init=False)

	def __post_init__(self) -> None:
		if self.path.exists():
			self._load_existing()
		else:
			self.data = {
				"board": self.board.as_dict(),
				"frames": [],
			}
			self._flush()

	def _load_existing(self) -> None:
		try:
			with self.path.open("r", encoding="utf-8") as fh:
				loaded = json.load(fh)
		except (json.JSONDecodeError, OSError) as exc:
			raise RuntimeError(f"Failed to load metadata file {self.path}") from exc

		frames = loaded.get("frames") if isinstance(loaded, dict) else None
		if not isinstance(frames, list):
			raise RuntimeError(
				f"Metadata file {self.path} is malformed; expected a 'frames' list."
			)

		if "board" not in loaded:
			loaded["board"] = self.board.as_dict()

		self.data = loaded

	@property
	def frames(self) -> List[Dict[str, object]]:
		return self.data.setdefault("frames", [])  # type: ignore[return-value]

	def next_frame_index(self) -> int:
		return len(self.frames)

	def make_image_name(self, index: int) -> str:
		return f"images/frame_{index:03d}.png"

	def add_frame(self, image_rel_path: str, joint_positions: List[float]) -> Dict[str, object]:
		timestamp = datetime.now(timezone.utc).isoformat()
		entry = {
			"timestamp": timestamp,
			"image": image_rel_path,
			"joint_positions": joint_positions,
		}
		self.frames.append(entry)
		self._flush()
		return entry

	def _flush(self) -> None:
		self.path.parent.mkdir(parents=True, exist_ok=True)
		temp_path = self.path.with_suffix(".tmp")
		with temp_path.open("w", encoding="utf-8") as fh:
			json.dump(self.data, fh, indent=2)
		temp_path.replace(self.path)


class TeleopLoop:
	"""Background loop that pumps the teleop controller at a fixed frequency."""

	def __init__(self, controller: TeleopController) -> None:
		self._controller = controller
		self._stop_event = threading.Event()
		self._thread: Optional[threading.Thread] = None

	def start(self) -> None:
		if self._thread and self._thread.is_alive():
			return

		self._stop_event.clear()

		def _run() -> None:
			LOGGER.info("Teleop loop started")
			period = 1.0 / max(1, getattr(self._controller, "teleop_hz", 50))
			while not self._stop_event.is_set():
				try:
					self._controller.teleop_step()
				except Exception:
					LOGGER.exception("Error during teleop step; continuing")
				time.sleep(period)
			LOGGER.info("Teleop loop stopped")

		self._thread = threading.Thread(target=_run, name="teleop_loop", daemon=True)
		self._thread.start()

	def stop(self, timeout: float = 2.0) -> None:
		self._stop_event.set()
		if self._thread:
			self._thread.join(timeout=timeout)
			if self._thread.is_alive():
				LOGGER.warning("Teleop loop thread did not terminate cleanly")
			self._thread = None


def _configure_logging(verbose: bool) -> None:
	level = logging.DEBUG if verbose else logging.INFO
	logging.basicConfig(
		level=level,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Capture Charuco calibration frames with synchronized joint position metadata."
		)
	)
	parser.add_argument(
		"--camera-url",
		required=True,
		help="HTTP URL to the ESP32 camera MJPEG stream",
	)
	parser.add_argument(
		"--camera-control-url",
		default=None,
		help="Optional base URL for camera control endpoints (defaults to stream host)",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=_default_output_root(),
		help="Directory where images/metadata will be stored",
	)
	parser.add_argument(
		"--no-window",
		action="store_true",
		help="Disable the finger slider preview window",
	)
	parser.add_argument(
		"--verbose",
		action="store_true",
		help="Enable debug logging",
	)
	parser.add_argument(
		"--gesture-config",
		type=Path,
		default=None,
		help="Optional path to a gesture configuration file for the finger slider",
	)
	parser.add_argument(
		"--camera-index",
		type=int,
		default=None,
		help="Local camera index for the finger slider hand-tracking input",
	)
	parser.add_argument(
		"--teleop-input",
		choices=["xbox", "keyboard", "finger", "finger-sliders"],
		default="finger-sliders",
		help="Which teleop input to use (default: finger-sliders)",
	)
	return parser.parse_args()


def _create_directories(root: Path) -> Path:
	images_dir = root / "images"
	images_dir.mkdir(parents=True, exist_ok=True)
	return images_dir


def _initialize_motion_service() -> MotionService:
	driver = CanDriver()
	motion_service = MotionService(driver=driver)
	motion_service.start()
	return motion_service


def _initialize_teleop(
	motion_service: MotionService,
	show_window: bool,
	gesture_config: Optional[Path],
	camera_index: Optional[int],
	teleop_input: str = "finger-sliders",
) -> TeleopController:
	# Select input controller implementation
	key = (teleop_input or "").lower()
	if key == "xbox":
		input_controller = XboxController()
	elif key == "keyboard":
		input_controller = KeyboardController()
	elif key == "finger":
		input_controller = FingerInput(camera_index=camera_index, show_window=show_window)
	else:
		# default: finger-sliders
		input_controller = FingerSliderInput(
			camera_index=camera_index,
			gesture_config_path=gesture_config,
			show_window=show_window,
		)
	driver = cast(Any, motion_service.driver)
	teleop = TeleopController(input_controller, driver, motion_service)
	# The controller starts in a paused state; resume so the operator can move immediately.
	try:
		teleop._resume_teleop()  # type: ignore[attr-defined]
	except AttributeError:
		LOGGER.warning("Teleop controller lacks _resume_teleop; continuing paused.")
	return teleop


def _capture_image(camera: IPCamera) -> np.ndarray:
	raw = camera.take_picture()
	array = np.frombuffer(raw, dtype=np.uint8)
	frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
	if frame is None:
		raise RuntimeError("Failed to decode image from IP camera")
	return frame


def _save_frame(image: np.ndarray, path: Path) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	if not cv2.imwrite(str(path), image):
		raise RuntimeError(f"Failed to write image to {path}")


def _read_joint_positions(motion_service: MotionService) -> List[float]:
	driver = getattr(motion_service, "driver", None)
	if driver is None:
		raise RuntimeError("Motion service has no driver assigned")
	feedback = driver.get_feedback()
	joints = feedback.get("q")
	if not isinstance(joints, list):
		raise RuntimeError("Driver feedback missing joint positions (q)")
	if len(joints) < 6:
		LOGGER.warning("Expected at least 6 joint positions, got %d", len(joints))
	return [float(v) for v in joints[:6]]


def _print_instructions(output_dir: Path) -> None:
	print(
		"\nCalibration capture ready. Use the finger slider teleop window to position the arm."
	)
	print("Press 'c' then Enter to capture a frame, 'q' then Enter to quit.\n")
	print(f"Images and metadata will be saved under: {output_dir}")


def main() -> None:
	args = _parse_args()
	_configure_logging(args.verbose)

	output_dir: Path = args.output_dir.resolve()
	images_dir = _create_directories(output_dir)
	metadata = CalibrationMetadata(output_dir / "metadata.json", BoardMetadata())

	motion_service: Optional[MotionService] = None
	teleop_loop: Optional[TeleopLoop] = None
	teleop_controller: Optional[TeleopController] = None
	camera: Optional[IPCamera] = None
	input_controller: Optional[FingerSliderInput] = None

	try:
		LOGGER.info("Starting motion service and teleoperation stack")
		motion_service = _initialize_motion_service()

		# Determine whether teleop must run in the main thread. Pygame-based
		# controllers (Xbox/Keyboard) require main-thread handling for their
		# event loop; additionally, the preview window requires OpenCV GUI calls
		# to run in the main thread.
		need_main_thread = (not args.no_window) or (args.teleop_input in ("xbox", "keyboard"))

		if need_main_thread:
			teleop_controller = _initialize_teleop(
				motion_service,
				show_window=True,
				gesture_config=args.gesture_config,
				camera_index=args.camera_index,
				teleop_input=args.teleop_input,
			)
			input_controller = teleop_controller.input_controller  # type: ignore[attr-defined]

			camera = IPCamera(args.camera_url, control_base_url=args.camera_control_url)
			_print_instructions(output_dir)

			# Command queue populated by reader thread
			cmd_queue: "Queue[str]" = Queue()
			stop_event = threading.Event()

			def _command_reader() -> None:
				# Prefer non-blocking console reads on Windows using msvcrt.
				if platform.system().lower().startswith("win") and msvcrt is not None:
					buf = ""
					while not stop_event.is_set():
						if msvcrt.kbhit():
							ch = msvcrt.getwch()
							# Enter/Return
							if ch in ("\r", "\n"):
								cmd_queue.put(buf.strip().lower())
								buf = ""
								continue
							# Ctrl-C
							if ch == "\x03":
								cmd_queue.put("^C")
								continue
							buf += ch
						else:
							time.sleep(0.05)
				else:
					# Fallback: blocking input() in a thread.
					while not stop_event.is_set():
						try:
							line = input()
						except EOFError:
							stop_event.set()
							break
						cmd_queue.put(line.strip().lower())

			reader_thread = threading.Thread(target=_command_reader, name="cmd_reader", daemon=True)
			reader_thread.start()

			# Main teleop loop runs here so GUI calls are on the main thread
			period = 1.0 / max(1, getattr(teleop_controller, "teleop_hz", 50))
			try:
				while not stop_event.is_set():
					teleop_controller.teleop_step()
					# Handle queued console commands
					cmd = None
					try:
						cmd = cmd_queue.get_nowait()
					except Empty:
						pass
					if cmd is not None:
						if cmd in {"q", "quit", "exit", "^c"}:
							LOGGER.info("Operator requested shutdown")
							break
						if cmd not in {"c", "capture", ""}:
							print("Unknown command; please enter 'c' to capture or 'q' to quit.")
						else:
							frame_index = metadata.next_frame_index()
							relative_image_path = metadata.make_image_name(frame_index)
							absolute_image_path = images_dir / Path(relative_image_path).name
							LOGGER.info("Capturing frame %03d", frame_index)
							frame = _capture_image(camera)
							_save_frame(frame, absolute_image_path)
							joints = _read_joint_positions(motion_service)
							metadata.add_frame(relative_image_path, joints)
							print(
								f"Captured frame_{frame_index:03d}: {absolute_image_path.name} with joints {joints}"
							)
				time.sleep(period)
			except KeyboardInterrupt:
				LOGGER.info("Interrupted by user; stopping main teleop loop")
			finally:
				stop_event.set()
				reader_thread.join(timeout=1.0)

		else:
			# No preview requested: keep previous behavior (teleop in background,
			# blocking input() in main thread).
			teleop_controller = _initialize_teleop(
				motion_service,
				show_window=False,
				gesture_config=args.gesture_config,
				camera_index=args.camera_index,
				teleop_input=args.teleop_input,
			)
			input_controller = teleop_controller.input_controller  # type: ignore[attr-defined]

			teleop_loop = TeleopLoop(teleop_controller)
			teleop_loop.start()

			camera = IPCamera(args.camera_url, control_base_url=args.camera_control_url)
			# Provide operator instructions once everything is running.
			_print_instructions(output_dir)

			while True:
				try:
					user_input = input("Command [c=Capture, q=Quit]: ").strip().lower()
				except EOFError:
					LOGGER.info("EOF received; stopping session")
					break

				if user_input in {"q", "quit", "exit"}:
					LOGGER.info("Operator requested shutdown")
					break

				if user_input not in {"c", "capture", ""}:
					print("Unknown command; please enter 'c' to capture or 'q' to quit.")
					continue

				frame_index = metadata.next_frame_index()
				relative_image_path = metadata.make_image_name(frame_index)
				absolute_image_path = images_dir / Path(relative_image_path).name

				LOGGER.info("Capturing frame %03d", frame_index)
				frame = _capture_image(camera)
				_save_frame(frame, absolute_image_path)
				joints = _read_joint_positions(motion_service)

				metadata.add_frame(relative_image_path, joints)
				print(
					f"Captured frame_{frame_index:03d}: {absolute_image_path.name} with joints {joints}"
				)

	except KeyboardInterrupt:
		LOGGER.info("Interrupted by user; shutting down")
	except Exception:
		# Ensure we log the full traceback so root causes are visible during teardown
		LOGGER.exception("Unhandled exception during capture session; shutting down")
		raise
	finally:
		LOGGER.info("Tearing down session")

		# Stop controller (stop active movements) first
		if teleop_controller:
			try:
				teleop_controller.stop_all()
			except Exception:
				LOGGER.exception("Error stopping teleop controller")

		# Close the input controller and release any camera resources so the
		# teleop thread (which calls get_events -> camera.read) can wake up and
		# exit. Closing input/camera first helps avoid join timeouts.
		if input_controller:
			try:
				input_controller.close()
			except Exception:
				LOGGER.exception("Error closing finger slider input")

		if camera:
			try:
				camera.release()
			except Exception:
				LOGGER.exception("Error releasing IP camera")

		# Now stop the teleop pump and wait for it to terminate
		if teleop_loop:
			try:
				teleop_loop.stop(timeout=8.0)
			except Exception:
				LOGGER.exception("Error stopping teleop loop")

		# Finally stop motion service / drivers
		if motion_service:
			try:
				motion_service.stop()
			except Exception:
				LOGGER.exception("Error stopping motion service")


if __name__ == "__main__":
	main()

