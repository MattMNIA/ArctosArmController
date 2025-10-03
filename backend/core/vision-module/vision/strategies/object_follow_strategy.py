from .base_strategy import BaseStrategy
from ..detectors.object_detector import ObjectDetector
from ..cameras.base_camera import BaseCamera
from typing import Any, Dict

class ObjectFollowStrategy(BaseStrategy):
    """Strategy for following detected objects in the camera feed."""

    def __init__(self, object_detector: ObjectDetector, camera: BaseCamera):
        super().__init__()
        self.object_detector = object_detector
        self.camera = camera
        self.target_object = None

    def start(self):
        self.camera.start()

    def stop(self):
        self.camera.stop()

    def execute(self):
        frame = self.camera.get_frame()
        if frame is not None:
            self.target_object = self.object_detector.detect(frame)
            if self.target_object:
                self._follow_target(self.target_object)

    def _follow_target(self, target):
        # Implement logic to adjust camera or system movement to follow the target
        pass

    def get_target(self):
        return self.target_object

    def set_target(self, target):
        self.target_object = target

    def on_gesture_detected(self, gesture):
        if gesture == "peace_sign":
            self.stop()  # Stop following when a peace sign is detected
            # Additional logic for handling peace sign gesture can be added here
