from vision.controllers.gesture_action_router import GestureActionRouter
from vision.gestures.peace_sign import PeaceSign

def test_peace_sign_action():
    router = GestureActionRouter()
    peace_sign = PeaceSign()

    # Simulate detecting a peace sign gesture
    gesture_detected = peace_sign.detect()

    # Route the action based on the detected gesture
    action = router.route_action(gesture_detected)

    # Assert that the action corresponds to stopping input and motor control
    assert action == "stop_input_and_motor_control"

def test_other_gesture_action():
    router = GestureActionRouter()
    # Simulate detecting a gesture that does not correspond to any action
    gesture_detected = "unknown_gesture"

    # Route the action based on the detected gesture
    action = router.route_action(gesture_detected)

    # Assert that no action is taken for unknown gestures
    assert action is None

def test_multiple_gestures():
    router = GestureActionRouter()
    peace_sign = PeaceSign()

    # Simulate detecting a peace sign gesture
    gesture_detected = peace_sign.detect()

    # Route the action based on the detected gesture
    action = router.route_action(gesture_detected)

    # Assert that the action corresponds to stopping input and motor control
    assert action == "stop_input_and_motor_control"

    # Simulate detecting another gesture
    gesture_detected = "another_gesture"
    action = router.route_action(gesture_detected)

    # Assert that the action for the second gesture is handled correctly
    assert action == "expected_action_for_another_gesture"  # Replace with actual expected action

def test_router_initialization():
    router = GestureActionRouter()
    assert router is not None
    assert isinstance(router, GestureActionRouter)