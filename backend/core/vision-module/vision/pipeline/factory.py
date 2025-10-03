from .controllers.pipeline_controller import PipelineController
from .detectors.finger_tracker import FingerTracker
from .detectors.hand_gesture_detector import HandGestureDetector
from .detectors.object_detector import ObjectDetector
from .strategies.finger_slider_strategy import FingerSliderStrategy
from .strategies.object_follow_strategy import ObjectFollowStrategy

class PipelineFactory:
    def __init__(self):
        self.detectors = {}
        self.strategies = {}

    def register_detector(self, name: str, detector):
        self.detectors[name] = detector

    def register_strategy(self, name: str, strategy):
        self.strategies[name] = strategy

    def create_pipeline(self, detector_name: str, strategy_name: str) -> PipelineController:
        if detector_name not in self.detectors:
            raise ValueError(f"Detector '{detector_name}' not registered.")
        if strategy_name not in self.strategies:
            raise ValueError(f"Strategy '{strategy_name}' not registered.")

        detector = self.detectors[detector_name]()
        strategy = self.strategies[strategy_name]()
        return PipelineController(detector, strategy)

# Example of registering detectors and strategies
factory = PipelineFactory()
factory.register_detector("finger_tracker", FingerTracker)
factory.register_detector("hand_gesture_detector", HandGestureDetector)
factory.register_detector("object_detector", ObjectDetector)
factory.register_strategy("finger_slider", FingerSliderStrategy)
factory.register_strategy("object_follow", ObjectFollowStrategy)