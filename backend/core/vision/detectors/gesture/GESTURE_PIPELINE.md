# Gesture Recognition Pipeline

This document explains how the gesture recognition system works, how to train new models, and how to add custom gestures.

## Overview

The gesture recognition pipeline consists of three main stages:

1. **Data Collection** - Capture hand landmark samples for each gesture class
2. **Model Training** - Train a classifier on the collected samples
3. **Runtime Recognition** - Use the trained model to detect gestures in real-time

## Directory Structure

```
backend/core/vision/detectors/gesture/
├── collect_gesture_dataset.py   # Data collection script
├── train_gesture_model.py       # Model training script
├── gesture_recognizer.py        # Runtime recognition module
├── gestures.yml                 # Gesture configuration (labels → events)
├── data/
│   └── gesture_dataset.csv      # Collected training samples
└── models/
    └── gesture_classifier.joblib # Trained model file
```

## Step 1: Collecting Gesture Data

### Using a Local Camera

```bash
cd backend/core/vision/detectors/gesture
python collect_gesture_dataset.py --camera 0 --samples 150
```

### Using an IP Camera

```bash
python collect_gesture_dataset.py --ip-camera "http://192.168.1.100:81/stream" --samples 150
```

### Collection Options

| Option | Default | Description |
|--------|---------|-------------|
| `--gestures` | `neutral rock_and_roll thumbs_down thumbs_up` | Gesture names to collect |
| `--samples` | `150` | Samples per gesture (per hand) |
| `--output` | `data/gesture_dataset.csv` | Output CSV path |
| `--camera` | `0` | Local camera index |
| `--ip-camera` | None | IP camera URL (overrides --camera) |
| `--min-confidence` | `0.75` | Minimum hand detection confidence |
| `--append` | `True` | Append to existing dataset |
| `--max-hands` | `2` | Maximum hands to track |

### Collection Controls

During collection, use these keyboard controls:

- **Space**: Toggle recording on/off
- **N**: Skip to next gesture
- **C**: Clear samples for current gesture and restart
- **Q** or **Esc**: Quit collection

### Tips for Good Data

1. **Vary lighting conditions** - Collect samples in different lighting
2. **Vary hand positions** - Move your hand around the frame
3. **Vary distances** - Near and far from camera
4. **Use both hands** - The system tracks handedness
5. **Hold poses steadily** - Ensure clean samples
6. **Collect negatives** - Always include "neutral" samples

## Step 2: Training the Model

### Basic Training

```bash
cd backend/core/vision/detectors/gesture
python train_gesture_model.py
```

### Training Options

| Option | Default | Description |
|--------|---------|-------------|
| `--dataset` | `data/gesture_dataset.csv` | Input dataset path |
| `--output` | `models/gesture_classifier.joblib` | Output model path |
| `--model-type` | `random_forest` | Classifier type (see below) |
| `--test-ratio` | `0.2` | Fraction for evaluation |
| `--trees` | `250` | Trees for forest-based models |
| `--max-depth` | None | Maximum tree depth |
| `--seed` | `42` | Random seed |
| `--force` | False | Overwrite existing model |
| `--tag` | None | Tag for versioned output |

### Available Model Types

| Type | Description | Best For |
|------|-------------|----------|
| `random_forest` | Random Forest ensemble | General use, good accuracy |
| `extra_trees` | Extra Trees ensemble | Fast training, similar to RF |
| `mlp` | Multi-layer Perceptron | Complex patterns |
| `logistic` | Logistic Regression | Simple, fast inference |
| `sgd` | Stochastic Gradient Descent | Large datasets |
| `naive_bayes` | Gaussian Naive Bayes | Very fast, baseline |

### Example: Training an MLP Model

```bash
python train_gesture_model.py --model-type mlp --force
```

### Model Output

The trained model is saved as a joblib file containing:

- `classifier` - The trained scikit-learn classifier
- `label_encoder` - Maps class indices to gesture labels
- `feature_names` - List of feature column names
- `metadata` - Training info (date, accuracy, etc.)

## Step 3: Configuring Gestures

Edit `gestures.yml` to map gesture labels to teleop events:

```yaml
model:
  path: models/gesture_classifier.joblib
  probability_threshold: 0.5    # Minimum confidence to accept
  smoothing_window: 3           # Frames for temporal smoothing
  min_consensus: 2              # Minimum agreeing frames
  max_history: 21               # History buffer size

gestures:
  - label: thumbs_up            # Must match training label
    event: teleop_resume        # Event sent to TeleopController
    hands_required: 1           # 1 = single hand, 2 = both hands
    hold_frames: 3              # Frames gesture must be held
    overlay: "Thumbs Up ➜ Resume"

  - label: thumbs_down
    event: teleop_pause
    hands_required: 1
    hold_frames: 3
    overlay: "Thumbs Down ➜ Pause"

  - label: rock_and_roll
    event: zero_all_joints
    hands_required: 1
    hold_frames: 3
    overlay: "Rock & Roll ➜ Zero"
```

### Supported Events

These events are handled by `TeleopController`:

| Event | Action |
|-------|--------|
| `teleop_pause` | Pause all teleoperation movement |
| `teleop_resume` | Resume teleoperation |
| `zero_all_joints` | Move all joints to zero position |

## Adding a New Gesture

### Step 1: Define the Gesture

Choose a unique, descriptive label (e.g., `peace_sign`, `open_palm`, `fist`).

### Step 2: Collect Training Data

```bash
python collect_gesture_dataset.py \
    --gestures neutral thumbs_up thumbs_down rock_and_roll peace_sign \
    --samples 200 \
    --append
```

Include all existing gestures plus your new one. The `--append` flag adds to the existing dataset.

### Step 3: Retrain the Model

```bash
python train_gesture_model.py --force
```

The `--force` flag overwrites the existing model. Without it, a timestamped version is created.

### Step 4: Add Configuration

Edit `gestures.yml`:

```yaml
gestures:
  # ... existing gestures ...

  - label: peace_sign
    event: my_custom_event
    hands_required: 1
    hold_frames: 3
    overlay: "Peace Sign ➜ Custom Action"
```

### Step 5: Handle the Event (Optional)

If your event isn't one of the built-in events, you'll need to add handling in the appropriate strategy class.

For finger tracking modes, edit `finger_touch_strategy.py`:

```python
def _process_gestures(self, hand_landmarks_list, handedness_list) -> None:
    # ... existing code ...

    for event in events:
        if event.event == "teleop_pause":
            # existing handling
        elif event.event == "my_custom_event":
            # Add your custom handling here
            with self._lock:
                self._pending_gesture_events.append(("press", "my_custom_token", 1.0))
            logger.info("Custom gesture detected!")
```

Then handle the token in `teleop_controller.py`:

```python
def _handle_special_event(self, event_type: str, token: str, scale: float) -> bool:
    # ... existing handlers ...

    if token == "my_custom_token":
        if event_type == 'press':
            self._do_custom_action()
        return True
```

## Feature Extraction

The `GestureFeatureExtractor` converts 21 MediaPipe hand landmarks into a normalized feature vector:

1. **Normalization**: All landmarks are normalized relative to the wrist (landmark 0)
2. **Scaling**: Distances are scaled by palm span for size invariance
3. **3D Coordinates**: Each landmark contributes (dx, dy, dz) features
4. **Handedness**: A binary flag indicates left (1.0) or right (0.0) hand

Total features: `21 landmarks × 3 coordinates + 1 handedness = 64 features`

## Temporal Smoothing

Raw predictions are noisy. The recognizer applies temporal smoothing:

1. **History Buffer**: Recent predictions are stored per hand
2. **Consensus Voting**: The most common label in the smoothing window wins
3. **Minimum Consensus**: A label must appear in at least `min_consensus` frames
4. **Hold Frames**: After consensus, the gesture must be held for `hold_frames` before triggering

## Troubleshooting

### Gesture Not Detected

1. **Check confidence**: Lower `probability_threshold` in `gestures.yml`
2. **Check lighting**: Ensure good, even lighting on hands
3. **Check pose**: Match the pose used during training
4. **Check logs**: Run with debug logging to see raw predictions

### False Positives

1. **Increase hold_frames**: Require longer gesture hold
2. **Increase min_consensus**: Require more agreeing frames
3. **Increase probability_threshold**: Require higher confidence
4. **Collect more negatives**: Add more "neutral" samples

### Model Not Loading

1. **Check path**: Ensure model file exists at configured path
2. **Check dependencies**: Install joblib, numpy, scikit-learn
3. **Check version**: Model may be incompatible with current scikit-learn

### Debug Logging

Enable debug logging to see gesture processing:

```python
import logging
logging.getLogger("backend.core.vision.detectors.gesture.gesture_recognizer").setLevel(logging.DEBUG)
```

## Complete Workflow Example

```bash
# 1. Navigate to gesture directory
cd backend/core/vision/detectors/gesture

# 2. Collect data (with IP camera)
python collect_gesture_dataset.py \
    --ip-camera "http://192.168.1.100:81/stream" \
    --gestures neutral thumbs_up thumbs_down rock_and_roll \
    --samples 200

# 3. Train model
python train_gesture_model.py --model-type mlp --force

# 4. Test in application
cd ../../../..
python app.py --teleop fingers --show-vision
```

## API Reference

### GestureRecognizer

```python
from gesture_recognizer import GestureRecognizer

recognizer = GestureRecognizer(
    config_path="gestures.yml",  # Optional: custom config
    model="mlp",                  # Optional: model type or path
)

# Process frame
events, overlays = recognizer.process(hand_landmarks, handedness_list)

for event in events:
    print(f"{event.change}: {event.event} ({event.label})")
```

### GestureEvent

```python
@dataclass
class GestureEvent:
    change: str        # "start" or "end"
    event: str         # e.g., "teleop_pause"
    label: str         # e.g., "thumbs_down"
    confidence: float  # 0.0 to 1.0
    overlay: str       # Display text
```
