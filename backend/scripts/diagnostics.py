#!/usr/bin/env python3
"""
Diagnostic script to measure performance bottlenecks in object centering pipeline.
Run this to isolate where the delay is coming from.
"""

import time
import logging
from pathlib import Path
from typing import Optional
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:
    cv2 = None
    logger.warning("OpenCV not available; display tests will be skipped")

try:
    import numpy as np
except ImportError:
    np = None
    logger.error("NumPy not available; cannot run diagnostics")
    exit(1)

from core.vision.cameras.ip_camera import IPCamera
from core.vision.detectors.object.object_detector import ObjectDetector
from core.vision.camera_manager import CameraManager

def time_camera_read(camera_url: str, num_frames: int = 100) -> float:
    """Time how long it takes to read frames from the camera."""
    if cv2 is None:
        logger.error("Cannot test camera read without OpenCV")
        return float('inf')

    cap = cv2.VideoCapture(camera_url)
    if not cap.isOpened():
        logger.error(f"Cannot open camera at {camera_url}")
        return float('inf')

    start_time = time.time()
    for _ in range(num_frames):
        ret, frame = cap.read()
        if not ret:
            logger.warning("Failed to read frame")
            break
    end_time = time.time()
    cap.release()

    fps = num_frames / (end_time - start_time)
    logger.info(f"Camera read FPS: {fps:.2f}")
    return fps

def time_detection(detector: ObjectDetector, num_frames: int = 50) -> float:
    """Time how long it takes to run detection."""
    start_time = time.time()
    for _ in range(num_frames):
        result = detector.detect(return_frame=False)
        if result is None:
            logger.warning("Detection failed")
    end_time = time.time()

    fps = num_frames / (end_time - start_time)
    logger.info(f"Detection FPS: {fps:.2f}")
    return fps

def time_display(frame, num_frames: int = 100) -> float:
    """Time how long it takes to display a frame."""
    if cv2 is None:
        logger.error("Cannot test display without OpenCV")
        return float('inf')

    window_name = "Diagnostic Display"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    start_time = time.time()
    for _ in range(num_frames):
        cv2.imshow(window_name, frame)
        cv2.waitKey(1)
    end_time = time.time()
    cv2.destroyWindow(window_name)

    fps = num_frames / (end_time - start_time)
    logger.info(f"Display FPS: {fps:.2f}")
    return fps

def main():
    # Configuration - adjust these paths/URLs as needed
    camera_config_path = Path(__file__).parent / "backend" / "config" / "default.yml"
    camera_url = "http://192.168.50.254:81/stream"  # Replace with actual URL

    logger.info("Starting object centering diagnostics...")

    # Test 1: Camera read speed
    logger.info("Testing camera read speed...")
    camera_fps = time_camera_read(camera_url, num_frames=100)
    if camera_fps == float('inf'):
        logger.error("Camera test failed")
        return

    # Test 2: Detection speed
    logger.info("Testing detection speed...")
    try:
        camera_manager = CameraManager(camera_config_path)
        detector = ObjectDetector(camera_manager, model="yolov8s.pt", confidence_threshold=0.3)
        detection_fps = time_detection(detector, num_frames=50)
    except Exception as e:
        logger.error(f"Detection test failed: {e}")
        return

    # Test 3: Display speed (if OpenCV available)
    if cv2 is not None and np is not None:
        logger.info("Testing display speed...")
        # Create a dummy frame
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        display_fps = time_display(dummy_frame, num_frames=100)
    else:
        display_fps = float('inf')

    # Summary
    logger.info("=== Performance Summary ===")
    logger.info(f"Camera FPS: {camera_fps:.2f}")
    logger.info(f"Detection FPS: {detection_fps:.2f}")
    if display_fps != float('inf'):
        logger.info(f"Display FPS: {display_fps:.2f}")

    # Analysis
    if detection_fps < 10:
        logger.warning("Detection is very slow (<10 FPS). Consider using a smaller model or GPU acceleration.")
    if camera_fps > 30 and detection_fps < 20:
        logger.warning("Camera is fast, but detection is the bottleneck.")
    if display_fps < 30 and display_fps != float('inf'):
        logger.warning("Display is slow. Try disabling display_feed in object centering.")

if __name__ == "__main__":
    main()