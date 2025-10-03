class BaseCamera:
    """Abstract base class for all camera implementations."""

    def __init__(self):
        self.is_running = False

    def start(self):
        """Start the camera."""
        raise NotImplementedError("Start method must be implemented by subclasses.")

    def stop(self):
        """Stop the camera."""
        raise NotImplementedError("Stop method must be implemented by subclasses.")

    def get_frame(self):
        """Get the current frame from the camera."""
        raise NotImplementedError("Get frame method must be implemented by subclasses.")

    def set_resolution(self, width: int, height: int):
        """Set the resolution of the camera."""
        raise NotImplementedError("Set resolution method must be implemented by subclasses.")

    def set_frame_rate(self, fps: int):
        """Set the frame rate of the camera."""
        raise NotImplementedError("Set frame rate method must be implemented by subclasses.")