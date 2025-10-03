from vision.pipeline.factory import PipelineFactory
from vision.detectors.finger_tracker import FingerTracker
from vision.detectors.hand_gesture_detector import HandGestureDetector
from vision.strategies.finger_slider_strategy import FingerSliderStrategy
from vision.strategies.object_follow_strategy import ObjectFollowStrategy
import unittest

class TestPipelineFactory(unittest.TestCase):

    def setUp(self):
        self.factory = PipelineFactory()

    def test_create_finger_slider_pipeline(self):
        pipeline = self.factory.create_pipeline(FingerSliderStrategy, FingerTracker)
        self.assertIsNotNone(pipeline)
        self.assertIsInstance(pipeline.strategy, FingerSliderStrategy)
        self.assertIsInstance(pipeline.detector, FingerTracker)

    def test_create_object_follow_pipeline(self):
        pipeline = self.factory.create_pipeline(ObjectFollowStrategy, HandGestureDetector)
        self.assertIsNotNone(pipeline)
        self.assertIsInstance(pipeline.strategy, ObjectFollowStrategy)
        self.assertIsInstance(pipeline.detector, HandGestureDetector)

    def test_invalid_pipeline_creation(self):
        with self.assertRaises(ValueError):
            self.factory.create_pipeline(None, FingerTracker)

    def test_pipeline_with_multiple_detectors(self):
        pipeline = self.factory.create_pipeline(FingerSliderStrategy, HandGestureDetector)
        self.assertIsNotNone(pipeline)
        self.assertIsInstance(pipeline.strategy, FingerSliderStrategy)
        self.assertIsInstance(pipeline.detector, HandGestureDetector)

if __name__ == '__main__':
    unittest.main()