from time import time

class Throttler:
    """Utility class to control the rate of function calls."""

    def __init__(self, rate: float):
        self.rate = rate  # Maximum calls per second
        self.last_called = 0.0

    def throttle(self, func):
        """Decorator to throttle the execution of a function."""
        def wrapper(*args, **kwargs):
            current_time = time()
            if current_time - self.last_called >= 1.0 / self.rate:
                self.last_called = current_time
                return func(*args, **kwargs)
        return wrapper

    def reset(self):
        """Reset the throttler to allow immediate function calls."""
        self.last_called = 0.0