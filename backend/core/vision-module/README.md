# Vision Module Documentation

## Overview

The Vision Module is designed to provide a flexible and modular camera and vision system for detecting gestures and controlling movements. It utilizes MediaPipe for hand and finger tracking, along with various detection algorithms for object recognition. The module is structured to allow easy integration of different movement strategies, detectors, and camera configurations.

## Purpose

The primary purpose of this module is to facilitate the development of applications that require real-time gesture recognition and movement control. By defining specific gestures and their corresponding actions, the system can respond dynamically to user inputs, enhancing interactivity and control.

## Features

- **Camera Control**: Supports various camera types and configurations, including resolution and frame rate adjustments.
- **Gesture Detection**: Implements detectors for finger tracking, hand gestures, and object detection.
- **Movement Strategies**: Allows for the definition of different movement strategies that can be easily switched based on detected gestures.
- **Modular Design**: Each component (camera, detector, strategy) is loosely coupled, making it easy to extend and maintain.

## Installation

To set up the Vision Module, ensure you have the required dependencies installed. You can install them using pip:

```
pip install opencv-python mediapipe
```

## Usage

1. **Camera Setup**: Configure the camera settings in the `cameras` directory. You can choose between different camera implementations by modifying the `camera_registry.py`.

2. **Gesture Detection**: Define gestures in the `gestures` directory. Each gesture can have specific actions associated with it, such as stopping input or controlling motors.

3. **Movement Strategies**: Implement movement strategies in the `strategies` directory. Strategies can be switched dynamically based on detected gestures.

4. **Pipeline Configuration**: Use the `pipeline` directory to bind detectors and strategies together, creating a cohesive processing flow.

## Example

To use the Vision Module, you can create a main application that initializes the camera, sets up the detectors, and starts processing frames. Here’s a simple example:

```python
from vision.cameras.camera_registry import CameraRegistry
from vision.detectors.hand_gesture_detector import HandGestureDetector
from vision.strategies.finger_slider_strategy import FingerSliderStrategy

# Initialize camera
camera = CameraRegistry.get_camera()
camera.start()

# Initialize gesture detector
gesture_detector = HandGestureDetector()

# Initialize movement strategy
movement_strategy = FingerSliderStrategy()

# Main loop
while True:
    frame = camera.get_frame()
    gestures = gesture_detector.detect(frame)
    movement_strategy.execute(gestures)
```

## Contributing

Contributions to the Vision Module are welcome! Please follow the standard practices for contributing to open-source projects, including forking the repository, making changes, and submitting a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.