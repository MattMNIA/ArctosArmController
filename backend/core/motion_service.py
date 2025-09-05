import threading
import time
import queue
from typing import Dict, Any, List, Optional, Callable, Protocol
import logging
from abc import ABC, abstractmethod
from core.drivers.sim_driver import SimDriver

logger = logging.getLogger(__name__)

class Command(ABC):
    """Abstract base class for all motion commands."""
    @abstractmethod
    def execute(self, driver) -> None:
        pass

    @abstractmethod
    def get_description(self) -> str:
        pass

class JointCommand(Command):
    """Command for joint movements."""
    def __init__(self, q: List[float], duration_s: float):
        self.q = q
        self.duration_s = duration_s

    def execute(self, driver) -> None:
        driver.send_joint_targets(self.q, self.duration_s)
        time.sleep(self.duration_s)

    def get_description(self) -> str:
        return f"Joint move: q={self.q}, duration={self.duration_s}s"

class GripperCommand(Command):
    """Command for gripper actions."""
    def __init__(self, action: str, position: Optional[float] = None):
        self.action = action
        self.position = position

    def execute(self, driver) -> None:
        if self.action == 'open':
            driver.open_gripper()
        elif self.action == 'close':
            driver.close_gripper()
        elif self.action == 'set' and self.position is not None:
            driver.set_gripper_position(self.position)
        time.sleep(0.1)  # Short delay for gripper actions

    def get_description(self) -> str:
        if self.action == 'set':
            return f"Gripper set: position={self.position}"
        return f"Gripper {self.action}"

class MotionService:
    """
    Manages motion commands via a queue and executes them in a separate thread.
    Ensures thread-safe operation and proper state management.
    """
    def __init__(self, driver=None, loop_hz: int = 50):
        self.driver = driver or SimDriver()
        self.loop_hz = loop_hz
        self.command_queue: "queue.Queue[Command]" = queue.Queue()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_state = "IDLE"
        self.ws_emit: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._lock = threading.Lock()  # For thread-safe state changes

    def start(self):
        """Start the motion service loop."""
        with self._lock:
            if self.running:
                logger.warning("MotionService is already running")
                return
            logger.info("Starting MotionService loop")
            self.running = True
            self.driver.connect()
            self.driver.enable()
            self.current_state = "RUNNING"
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the motion service loop."""
        with self._lock:
            if not self.running:
                logger.warning("MotionService is not running")
                return
            logger.info("Stopping MotionService loop")
            self.current_state = "STOPPING"
            self.running = False
            if self.thread:
                self.thread.join(timeout=5.0)
            self.driver.disable()
            self.current_state = "IDLE"
            logger.info("MotionService stopped")

    def enqueue(self, cmd: Command):
        """Enqueue a command for execution."""
        logger.info(f"Enqueued command: {cmd.get_description()}")
        self.command_queue.put(cmd)

    def _loop(self):
        """Main execution loop."""
        dt = 1.0 / self.loop_hz
        while self.running:
            try:
                cmd = self.command_queue.get(timeout=dt)
                logger.info(f"Retrieved command: {cmd.get_description()}")
                self._execute(cmd)
            except queue.Empty:
                pass
            # Always emit telemetry
            feedback = self.driver.get_feedback()
            self._emit_status(feedback)
            time.sleep(dt)

    def _execute(self, cmd: Command):
        """Execute a command with error handling."""
        try:
            logger.info(f"Executing: {cmd.get_description()}")
            with self._lock:
                self.current_state = "EXECUTING"
            cmd.execute(self.driver)
            with self._lock:
                self.current_state = "IDLE"
            logger.info("Execution complete")
        except Exception as e:
            logger.error(f"Error executing command {cmd.get_description()}: {e}")
            with self._lock:
                self.current_state = "ERROR"
            # Optionally, emit error status or handle recovery

    def _emit_status(self, feedback: Dict[str, Any]):
        """Emit status via WebSocket."""
        limits = feedback.get("limits", [])
        for i, lim in enumerate(limits):
            if any(lim):
                logger.warning(f"Limit switch hit on servo {i+1}: IN1={lim[0]}, IN2={lim[1]}")
        event = {
            "state": self.current_state,
            "q": feedback.get("q", []),
            "faults": feedback.get("faults", []),
            "limits": limits,
            "mode": "SIM" if isinstance(self.driver, SimDriver) else "HW"
        }
        if self.ws_emit:
            self.ws_emit("telemetry", event)

    def open_gripper(self):
        """Enqueue a command to open the gripper."""
        cmd = GripperCommand('open')
        self.enqueue(cmd)

    def close_gripper(self):
        """Enqueue a command to close the gripper."""
        cmd = GripperCommand('close')
        self.enqueue(cmd)

    def set_gripper_position(self, position: float):
        """Enqueue a command to set the gripper position."""
        cmd = GripperCommand('set', position)
        self.enqueue(cmd)

    def send_joint_targets(self, q: List[float], duration_s: float = 1.0):
        """Enqueue a joint movement command."""
        cmd = JointCommand(q, duration_s)
        self.enqueue(cmd)
