# Developer Guide

This document explains the **code organization**, **module interactions**, and **logical flows** of the robotic arm control system.

---

## 🗂 Project Structure

````

backend/
│ app.py                # Flask app + SocketIO integration
│
├── core/
│   ├── motion\_service.py  # Background loop that executes commands
│   ├── drivers/
│   │   ├── base.py        # Driver ABC (interface contract)
│   │   ├── sim\_driver.py  # Simulation driver (prints + dummy telemetry)
│   │   └── can\_driver.py  # Real CAN bus driver
│   └── ik/
│       └── base.py        # IK Solver ABC
│
├── utils/
│   └── logger.py          # Centralized logging module
│
frontend/
│ src/pages/RobotControl.tsx  # Minimal UI for sending commands & viewing telemetry

````

---

## 🔄 Module Connections

- **Frontend UI** → sends commands to **Flask REST API** (`/api/execute`)
- **Flask app** → enqueues commands into **MotionService**
- **MotionService** → runs background loop, pops commands, calls **Driver**
- **Driver** → executes movement (simulation or real CAN hardware)
- **MotionService** → periodically collects telemetry from driver, pushes to **WebSocket**
- **Frontend UI** → subscribes to telemetry & displays status

---

## 📜 Sequence Flow (Command Execution)

```text
[React UI] --(POST /api/execute)--> [Flask API]
   [Flask API] --(enqueue)--> [MotionService Queue]
   [MotionService Loop] --(dequeue)--> [Driver]
   [Driver] --(executes joint move)--> (Simulation or Hardware)
   [Driver] --(feedback)--> [MotionService]
   [MotionService] --(emit telemetry)--> [WebSocket]
   [React UI] <--(telemetry)-- [WebSocket]
````

---

## 📜 Sequence Flow (Telemetry Update)

```text
[MotionService Loop] --> [Driver.get_feedback()]
[Driver] --> Returns joint positions, state
[MotionService] --> Emits telemetry JSON
[React UI] --> Displays live state/joints
```

---

## 🔍 Important Components

### `MotionService`

* Runs in a separate thread
* Uses a **queue** for commands
* Periodically polls driver feedback
* Emits telemetry events via WebSocket

### `Driver` Interface

Defined in `drivers/base.py`:

```python
class Driver(Protocol):
    def connect(self): ...
    def enable(self): ...
    def disable(self): ...
    def home(self): ...
    def send_joint_targets(self, q: List[float], t_s: float): ...
    def get_feedback(self) -> Dict[str, Any]: ...
    def estop(self): ...
```

This ensures `SimDriver` and `CanDriver` are **drop-in interchangeable**.

### `IKSolver`

* Currently a stub (just echoes values).
* Later: will compute joint configs from target poses.
* Important: **does not directly move the robot** — it just returns joint configs for MotionService.

---

## 🔮 Future Development

* **IK Module:** Numerical solver, plug into `/api/ik/solve`.
* **CAN Driver:** Replace SimDriver with python-can-based driver.
* **3D Simulation:** React-three-fiber visualization of joints.
* **Logging Feed:** Add WebSocket handler for logs → React log console.
* **Safety Layer:** Estop, bounds checking, collision detection.

---

## 🧭 Design Principles

* **Modularity:** IK, Drivers, MotionService, and UI are separate layers.
* **Single Responsibility:** Each module handles one concern.
* **Hot-swappable drivers:** You can swap `SimDriver` ↔ `CanDriver` with no other code changes.
* **Testability:** The whole stack works in simulation before real hardware.

```
