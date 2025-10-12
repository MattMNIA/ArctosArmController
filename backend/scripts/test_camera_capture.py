from __future__ import annotations

import argparse
import sys
from typing import Optional

import cv2
import numpy as np
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.vision.cameras.ip_camera import IPCamera
from core.vision.cameras.local_camera import LocalCamera


def decode_image(image_bytes: bytes) -> Optional[np.ndarray]:
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    return image


def display_image(image: np.ndarray, window_title: str) -> None:
    cv2.imshow(window_title, image)
    print("Press any key in the image window to close...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def capture_with_local_camera(camera_index: Optional[int]) -> None:
    camera = LocalCamera(camera_index=camera_index)
    try:
        image_bytes = camera.take_picture()
    finally:
        camera.release()

    image = decode_image(image_bytes)
    if image is None:
        raise RuntimeError("Failed to decode captured image from local camera.")

    display_image(image, "Local Camera Capture")


def capture_with_ip_camera(url: str, control_base_url: Optional[str], timeout: float) -> None:
    camera = IPCamera(url=url, control_base_url=control_base_url, timeout=timeout)
    try:
        image_bytes = camera.take_picture()
    finally:
        camera.release()

    image = decode_image(image_bytes)
    if image is None:
        raise RuntimeError("Failed to decode captured image from IP camera.")

    display_image(image, "IP Camera Capture")


def parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture and display a single frame from either a local or IP camera."
    )
    subparsers = parser.add_subparsers(dest="camera_type", required=True)

    local_parser = subparsers.add_parser("local", help="Use a local webcam (OpenCV VideoCapture)")
    local_parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="Camera index to open (default: auto-select).",
    )

    ip_parser = subparsers.add_parser("ip", help="Use an ESP32-style IP camera stream")
    ip_parser.add_argument("url", help="Stream URL for the IP camera (e.g., http://camera/stream)")
    ip_parser.add_argument(
        "--control-base",
        dest="control_base",
        default=None,
        help="Optional control base URL if different from the stream host",
    )
    ip_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds when calling the camera API (default: 5.0)",
    )

    return parser.parse_args(args)


def main() -> None:
    args = parse_args(sys.argv[1:])

    if args.camera_type == "local":
        capture_with_local_camera(camera_index=args.index)
    elif args.camera_type == "ip":
        capture_with_ip_camera(url=args.url, control_base_url=args.control_base, timeout=args.timeout)
    else:
        raise ValueError(f"Unsupported camera type: {args.camera_type}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - direct CLI feedback
        print(f"Error: {exc}")
        sys.exit(1)
