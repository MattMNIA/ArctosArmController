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
* **Teleoperation control** with keyboard and Xbox controller support

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

### Setup
1. Ensure pygame is installed: `pip install pygame`
2. For Xbox controller, connect via USB or Bluetooth
3. Run teleoperation: Access via API endpoint or integrated UI

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
