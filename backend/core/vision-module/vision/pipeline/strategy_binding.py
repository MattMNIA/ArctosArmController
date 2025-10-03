from typing import Dict, Callable, Any

class StrategyBinding:
    """Manages the binding of specific strategies to gestures."""

    def __init__(self):
        self._gesture_to_strategy: Dict[str, Callable[[], None]] = {}

    def bind_gesture(self, gesture: str, strategy: Callable[[], None]) -> None:
        """Bind a gesture to a specific movement strategy."""
        self._gesture_to_strategy[gesture] = strategy

    def unbind_gesture(self, gesture: str) -> None:
        """Unbind a gesture from its associated strategy."""
        if gesture in self._gesture_to_strategy:
            del self._gesture_to_strategy[gesture]

    def execute_strategy(self, gesture: str) -> Any:
        """Execute the strategy associated with the given gesture."""
        strategy = self._gesture_to_strategy.get(gesture)
        if strategy:
            return strategy()
        return None

    def get_bound_strategies(self) -> Dict[str, Callable[[], None]]:
        """Return a dictionary of currently bound gestures and their strategies."""
        return self._gesture_to_strategy.copy()