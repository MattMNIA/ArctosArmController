from __future__ import annotations

import sys
from pathlib import Path

import pytest  # type: ignore[import]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.vision.gesture_recognizer import (  # noqa: E402
    GestureActionConfig,
    GestureActionManager,
    HandPrediction,
)


def test_single_hand_activation_and_release():
    manager = GestureActionManager(
        [GestureActionConfig(label="rock_and_roll", event="zero_all_joints", hold_frames=3)]
    )

    # Initial state should not emit events
    assert manager.update({}) == []

    # Not enough frames yet
    manager.update({"Left": HandPrediction("rock_and_roll", 0.9)})
    manager.update({"Left": HandPrediction("rock_and_roll", 0.85)})
    events = manager.update({"Left": HandPrediction("rock_and_roll", 0.88)})
    assert events and events[0].change == "start"
    assert events[0].event == "zero_all_joints"

    # Removing the hand releases the gesture
    events = manager.update({})
    assert events and events[0].change == "end"
    assert events[0].event == "zero_all_joints"


def test_two_hand_activation_requires_both_hands():
    manager = GestureActionManager(
        [
            GestureActionConfig(
                label="thumbs_up",
                event="teleop_resume",
                hands_required=2,
                hold_frames=2,
                allowed_hands=["Left", "Right"],
            )
        ]
    )

    # Only left hand -> no activation
    manager.update({"Left": HandPrediction("thumbs_up", 0.92)})
    events = manager.update({"Left": HandPrediction("thumbs_up", 0.94)})
    assert events == []

    # Add right hand for sufficient frames
    manager.update(
        {
            "Left": HandPrediction("thumbs_up", 0.95),
            "Right": HandPrediction("thumbs_up", 0.91),
        }
    )
    events = manager.update(
        {
            "Left": HandPrediction("thumbs_up", 0.96),
            "Right": HandPrediction("thumbs_up", 0.93),
        }
    )
    assert events and events[0].event == "teleop_resume"
    assert events[0].change == "start"

    # Losing one hand should release the gesture
    events = manager.update({"Left": HandPrediction("thumbs_up", 0.9)})
    assert events and events[0].change == "end"
    assert events[0].event == "teleop_resume"


if __name__ == "__main__":
    pytest.main([__file__])
