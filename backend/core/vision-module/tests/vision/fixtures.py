from typing import Dict, Any

def get_camera_fixture() -> Dict[str, Any]:
    return {
        "camera_type": "OpenCVCamera",
        "resolution": (640, 480),
        "frame_rate": 30,
    }

def get_detector_fixtures() -> Dict[str, Any]:
    return {
        "finger_tracker": {
            "type": "FingerTracker",
            "detection_confidence": 0.7,
        },
        "hand_gesture_detector": {
            "type": "HandGestureDetector",
            "detection_confidence": 0.7,
        },
        "object_detector": {
            "type": "ObjectDetector",
            "model": "yolo",
        },
    }

def get_strategy_fixtures() -> Dict[str, Any]:
    return {
        "finger_slider_strategy": {
            "type": "FingerSliderStrategy",
            "gesture_actions": {
                "peace_sign": "stop_input_and_motor_control",
            },
        },
        "object_follow_strategy": {
            "type": "ObjectFollowStrategy",
            "gesture_actions": {
                "peace_sign": "stop_input_and_motor_control",
            },
        },
    }