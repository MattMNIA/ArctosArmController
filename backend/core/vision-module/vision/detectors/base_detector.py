class BaseDetector:
    """Abstract base class for all detectors in the vision module."""

    def process_frame(self, frame):
        """Process a single frame and return detection results.

        Args:
            frame: The input frame to process.

        Returns:
            A dictionary containing detection results.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    def reset(self):
        """Reset the detector's state."""
        pass

    def configure(self, **kwargs):
        """Configure the detector with specific parameters.

        Args:
            **kwargs: Configuration parameters for the detector.
        """
        pass