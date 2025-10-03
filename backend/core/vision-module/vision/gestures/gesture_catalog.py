from typing import Dict, Callable

class GestureCatalog:
    def __init__(self):
        self.gestures: Dict[str, Callable] = {}

    def register_gesture(self, name: str, action: Callable) -> None:
        self.gestures[name] = action

    def get_action(self, name: str) -> Callable:
        return self.gestures.get(name)

    def list_gestures(self) -> Dict[str, Callable]:
        return self.gestures

# Example of registering gestures and their actions
def stop_input_and_motor_control():
    print("Stopping input and motor control.")

# Create an instance of GestureCatalog
gesture_catalog = GestureCatalog()

# Register the peace sign gesture with its corresponding action
gesture_catalog.register_gesture("peace_sign", stop_input_and_motor_control)