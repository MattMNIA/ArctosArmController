class BaseStrategy:
    """Abstract base class for movement strategies in the vision system."""

    def start(self) -> None:
        """Start the movement strategy."""
        raise NotImplementedError("Start method must be implemented by subclasses.")

    def stop(self) -> None:
        """Stop the movement strategy."""
        raise NotImplementedError("Stop method must be implemented by subclasses.")

    def execute(self) -> None:
        """Execute the movement strategy."""
        raise NotImplementedError("Execute method must be implemented by subclasses.")

    def on_gesture_detected(self, gesture: str) -> None:
        """Handle detected gestures and perform corresponding actions."""
        raise NotImplementedError("on_gesture_detected method must be implemented by subclasses.")