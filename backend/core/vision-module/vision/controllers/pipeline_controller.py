from typing import List, Dict, Any, Optional

class PipelineController:
    """Manages the flow of data through the vision processing pipeline."""

    def __init__(self, detectors: List[Any], strategies: List[Any]) -> None:
        self.detectors = detectors
        self.strategies = strategies
        self.active_strategy = None

    def start_pipeline(self) -> None:
        """Starts the vision processing pipeline."""
        for detector in self.detectors:
            detector.start()

    def stop_pipeline(self) -> None:
        """Stops the vision processing pipeline."""
        for detector in self.detectors:
            detector.stop()

    def process_frame(self, frame: Any) -> None:
        """Processes a single frame through the pipeline."""
        for detector in self.detectors:
            results = detector.process(frame)
            self.handle_detection_results(results)

    def handle_detection_results(self, results: Dict[str, Any]) -> None:
        """Handles the results from detectors and invokes strategies."""
        for strategy in self.strategies:
            if strategy.should_execute(results):
                self.active_strategy = strategy
                strategy.execute(results)

    def set_active_strategy(self, strategy: Any) -> None:
        """Sets the active movement strategy."""
        if self.active_strategy:
            self.active_strategy.stop()
        self.active_strategy = strategy
        self.active_strategy.start()

    def get_active_strategy(self) -> Optional[Any]:
        """Returns the currently active strategy."""
        return self.active_strategy

    def close(self) -> None:
        """Cleans up resources used by the pipeline."""
        self.stop_pipeline()
        for detector in self.detectors:
            detector.close()