import threading
import time
import queue
from typing import Dict, Any, List, Optional, Callable
import logging
from core.drivers.sim_driver import SimDriver

logger = logging.getLogger(__name__)

class MotionCommand:
    def __init__(self, q: List[float], duration_s: float, simulate: bool = True):
        self.q = q
        self.duration_s = duration_s
        self.simulate = simulate

class MotionService:
    def __init__(self, driver=None, loop_hz: int = 50):
        self.driver = driver or SimDriver()
        self.loop_hz = loop_hz
        self.command_queue: "queue.Queue[MotionCommand]" = queue.Queue()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_state = "IDLE"
        self.ws_emit: Optional[Callable[[str, Dict[str, Any]], None]] = None  # injected by Flask/socketio

    def start(self):
        logger.info("Starting MotionService loop")
        self.running = True
        self.driver.connect()
        self.driver.enable()
        logger.info("MotionService state: RUNNING")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        logger.info("Stopping MotionService loop")
        logger.info("MotionService state: STOPPING")
        self.running = False
        if self.thread:
            self.thread.join()
        self.driver.disable()
        logger.info("MotionService stopped")

    def enqueue(self, cmd: MotionCommand):
        logger.info(f"Enqueued command: q={cmd.q}, duration={cmd.duration_s}s")
        self.command_queue.put(cmd)

    def _loop(self):
        dt = 1.0 / self.loop_hz
        while self.running:
            try:
                cmd = self.command_queue.get(timeout=dt)
                logger.info("Retrieved command from queue")
                logger.info("Queue size after get: %d", self.command_queue.qsize())
                self._execute(cmd)
            except queue.Empty:
                pass
            # always emit telemetry
            feedback = self.driver.get_feedback()
            self._emit_status(feedback)
            time.sleep(dt)

    def _execute(self, cmd: MotionCommand):
        logger.info(f"Executing command {cmd.q} over {cmd.duration_s}s")
        logger.info("MotionService state: EXECUTING")
        self.current_state = "EXECUTING"
        self.driver.send_joint_targets(cmd.q, cmd.duration_s)
        time.sleep(cmd.duration_s)
        self.current_state = "IDLE"
        logger.info("Execution complete")
        logger.info("MotionService state: IDLE")

    def _emit_status(self, feedback: Dict[str, Any]):
        event = {
            "state": self.current_state,
            "q": feedback.get("q", []),
            "faults": feedback.get("faults", []),
            "mode": "SIM" if isinstance(self.driver, SimDriver) else "HW"
        }
        if self.ws_emit:
            self.ws_emit("telemetry", event)
