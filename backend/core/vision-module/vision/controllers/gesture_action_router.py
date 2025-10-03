class GestureActionRouter:
    """Maps detected gestures to specific actions for different movement strategies."""

    def __init__(self):
        self.gesture_actions = {
            "peace_sign": self.stop_input_and_motor_control,
            # Add more gestures and their corresponding actions here
        }

    def route_gesture(self, gesture_name: str):
        """Routes the detected gesture to the corresponding action."""
        action = self.gesture_actions.get(gesture_name)
        if action:
            action()

    def stop_input_and_motor_control(self):
        """Stops input and motor control when a peace sign gesture is detected."""
        print("Stopping input and motor control due to peace sign gesture.")

    # Additional methods for other gestures can be defined here
