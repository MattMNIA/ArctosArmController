# Robotic Arm Control System (MVP)

This project is a modular control system for a robotic arm, built with:

- **Backend:** Python Flask + Flask-SocketIO
- **Frontend:** ReactJS
- **Drivers:** Interchangeable drivers (SimDriver for simulation, CanDriver for hardware)
- **Communication Protocol:** CAN Bus (via `python-can`)

The system is designed to be **modular and extensible**, so features like inverse kinematics (IK), gesture control, and computer vision can be integrated later.

---

## 🚀 Getting Started

### Backend
```bash
cd backend
pip install -r requirements.txt
python app.py
````

Backend runs at [http://localhost:5000](http://localhost:5000).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at [http://localhost:5173](http://localhost:5173).

---

## 🧩 Current Features

* REST API endpoint to **enqueue motion commands**
* **WebSocket telemetry** feed (state + joint positions)
* **Simulation driver** (`SimDriver`) for safe testing
* Basic React UI for sending commands and viewing telemetry
* **Teleoperation control** with keyboard, Xbox controller, and finger-gesture inputs

---

## 🎮 Teleoperation Controls

The system supports real-time teleoperation control for precise robotic arm manipulation.

### Keyboard Controls
- **WASD**: Move arm in XY plane
- **QE**: Rotate base
- **RF**: Control elbow and wrist
- **Space**: Emergency stop
- **ESC**: Exit teleoperation mode

### Xbox Controller Controls
- **Left Stick**: XY plane movement
- **Right Stick**: Elbow and wrist control
- **Left Trigger**: Rotate base counterclockwise
- **Right Trigger**: Rotate base clockwise
- **A Button**: Emergency stop
- **B Button**: Exit teleoperation mode

### Finger Gesture (Toggle) Controls
Thumb–finger pinches map directly to joint velocity presses. Touch a finger to move a joint, release to stop.

- **Thumb + Index**: Joint 0 forward (right hand) / Joint 0 reverse (left hand)
- **Thumb + Middle**: Joint 1
- **Thumb + Ring**: Joint 2
- **Thumb + Pinky**: Joint 3
- Movement direction depends on the hand you present to the camera.

Start with:

```bash
python app.py --drivers pybullet --teleop fingers
```

### Finger Slider Controls
Pinch the thumb and a finger, then move while holding the pinch to command two joints as proportional sliders:

- **Thumb + Index**: Horizontal motion controls Joint 0, vertical motion controls Joint 1
- **Thumb + Middle**: Horizontal motion controls Joint 2, vertical motion controls Joint 3
- **Thumb + Ring**: Horizontal motion controls Joint 4, vertical motion controls Joint 5
- **Thumb + Pinky**: Vertical motion opens/closes the gripper (up = open, down = close)

Grip is re-centered each time you release and re-pin. Movements are smoothed and accept subtle adjustments.
The preview automatically refreshes its wrist-based reference about once per second; press `R` at any time to force an immediate recalibration if you change your working distance.

Start with:

```bash
python app.py --drivers pybullet --teleop finger-sliders
```

Both finger-based modes scan for available cameras at startup. If more than one camera is detected, you'll be prompted to choose which one to use.

#### Gesture actions (finger sliders)

The finger slider pipeline now recognises high-level gestures to streamline common tasks:

- **Rock & roll** (any hand) &rarr; Zero all joints (sends them to `[0,0,0,0,0,0]`).
- **Double thumbs down** &rarr; Pause teleoperation and freeze all active velocities.
- **Double thumbs up** &rarr; Resume teleoperation after a pause.

You can customise these mappings in `backend/config/gestures.yml`.

#### Training your own gestures

Collect samples and retrain the classifier whenever you want to add or adjust gestures:

```bash
# 1. Record landmarks for each gesture plus a relaxed "neutral" pose
python scripts/collect_gesture_dataset.py --gestures neutral rock_and_roll thumbs_down thumbs_up --samples 200

# 2. Train the classifier and export it to models/gesture_classifier.joblib
python scripts/train_gesture_model.py --dataset data/gesture_dataset.csv
```

Keep the neutral class out of `gestures.yml`; it teaches the classifier what “no gesture” looks like so relaxed hands do not trigger an action. Update the config thresholds if you need an even higher confidence bar.

Edit `backend/config/gestures.yml` to point at the model file and map classifier labels to teleop actions. The backend hot-loads the configuration on startup; restart the teleop process after training to pick up a new model.

### Setup
1. Ensure pygame is installed: `pip install pygame`
2. For Xbox controller, connect via USB or Bluetooth
3. Run teleoperation: Access via API endpoint, integrated UI, or the `--teleop` CLI flag shown above

### Calibration
The Xbox controller automatically calibrates deadzones on startup to prevent stick drift. Triggers use a 0.5 threshold to ensure clean release behavior.

## 📡 Example Usage

**Send a move command**

```bash
POST /api/execute
{
  "mode": "joint",
  "target": { "q": [0, 0.5, -0.2, 0, 0, 0] },
  "duration_s": 2.0,
  "simulate": true
}
```

**Subscribe to telemetry (WebSocket)**

```js
socket.on("telemetry", (data) => {
  console.log("Current state:", data.state, "Joints:", data.q);
});
```

---

## 🔮 Roadmap

* Add **Inverse Kinematics solver** (`IKSolver`)
