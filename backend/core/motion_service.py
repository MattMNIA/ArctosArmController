import threading
import time
import queue
from typing import Dict, Any, List, Optional, Callable, Protocol, Union
import logging
from abc import ABC, abstractmethod
from core.drivers.sim_driver import SimDriver
from core.drivers.can_driver import CanDriver
from core.drivers.composite_driver import CompositeDriver

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
        """Start the joint movement (non-blocking)."""
        driver.send_joint_targets(self.q, self.duration_s)

    def get_description(self) -> str:
        return f"Joint move: q={self.q}, duration={self.duration_s}s"

class GripperCommand(Command):
    """Command for gripper actions."""
    def __init__(self, action: str, position: Optional[float] = None, delay: float = 0.5):
        self.action = action
        self.position = position
        self.delay = delay

    def execute(self, driver) -> None:
        if self.action == 'open':
            driver.open_gripper()
        elif self.action == 'close':
            driver.close_gripper()
        elif self.action == 'set' and self.position is not None:
            driver.set_gripper_position(self.position)


    def get_description(self) -> str:
        if self.action == 'set':
            return f"Gripper set: position={self.position}, delay={self.delay:.2f}s"
        return f"Gripper {self.action}, delay={self.delay:.2f}s"

class HomeCommand(Command):
    """Command for homing specific joints."""
    def __init__(self, joint_indices: List[int]):
        self.joint_indices = joint_indices

    def execute(self, driver) -> None:
        """Home the specified joints."""
        driver.home_joints(self.joint_indices)

    def get_description(self) -> str:
        return f"Home joints: {self.joint_indices}"

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
        
        # Use separate locks for different data
        self._state_lock = threading.Lock()  # For state changes
        self._command_lock = threading.Lock()  # For current command
        
        self._current_state = "IDLE"
        self.ws_emit: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.has_active_connections: Optional[Callable[[], bool]] = None
        self._paused = False  # Flag to freeze execution on limit hit
        self._current_command: Optional[Command] = None
        self._command_start_time = 0.0
        self._current_gripper_position = 0.0  # Track gripper position (0.0-1.0 range)

    @property
    def current_state(self):
        with self._state_lock:
            return self._current_state
    
    @current_state.setter
    def current_state(self, value):
        with self._state_lock:
            self._current_state = value
    
    @property
    def paused(self):
        with self._state_lock:
            return self._paused
    
    @paused.setter
    def paused(self, value):
        with self._state_lock:
            self._paused = value

    def start(self):
        """Start the motion service loop."""
        with self._state_lock:
            if self.running:
                logger.warning("MotionService is already running")
                return
            logger.info("Starting MotionService loop")
            self.running = True
            self._paused = False  # Reset paused on start
            self._current_state = "RUNNING"
        
        # Initialize driver outside of lock
        try:
            self.driver.connect()
            self.driver.enable()
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        except Exception as e:
            logger.error(f"Failed to start motion service: {e}")
            with self._state_lock:
                self.running = False
                self._current_state = "ERROR"
            raise

    def stop(self):
        """Stop the motion service loop."""
        with self._state_lock:
            if not self.running:
                logger.warning("MotionService is not running")
                return
            logger.info("Stopping MotionService loop")
            self._current_state = "STOPPING"
            self.running = False
            self._paused = False  # Reset paused on stop
        
        # Wait for thread and cleanup outside of lock
        if self.thread:
            self.thread.join(timeout=5.0)
        
        try:
            self.driver.disable()
        except Exception as e:
            logger.error(f"Error disabling driver: {e}")
        
        self.current_state = "IDLE"
        logger.info("MotionService stopped")

    def enqueue(self, cmd: Command):
        """Enqueue a command for execution."""
        logger.info(f"Enqueued command: {cmd.get_description()}")
        if self.paused:
            self.paused = False
            logger.info("Resuming execution after limit hit due to new command.")
        self.command_queue.put(cmd)

    def clear_queue(self):
        """Clear the command queue."""
        cleared_count = 0
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
                cleared_count += 1
            except queue.Empty:
                break
        logger.info(f"Command queue cleared. Removed {cleared_count} commands due to limit hit.")

    def _cancel_pending_gripper_commands(self):
        """Remove any pending gripper commands from the queue."""
        # Create a new queue with non-gripper commands
        new_queue = queue.Queue()
        cancelled_count = 0
        while not self.command_queue.empty():
            try:
                cmd = self.command_queue.get_nowait()
                if isinstance(cmd, GripperCommand):
                    cancelled_count += 1
                    logger.info(f"Cancelled pending gripper command: {cmd.get_description()}")
                else:
                    new_queue.put(cmd)
            except queue.Empty:
                break
        self.command_queue = new_queue
        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} pending gripper commands")

    def _loop(self):
        """Main execution loop."""
        dt = 1.0 / self.loop_hz
        while self.running:
            try:
                # Check for new commands (non-blocking)
                current_cmd = None
                with self._command_lock:
                    current_cmd = self._current_command
                
                if current_cmd is None and not self.paused:
                    try:
                        cmd = self.command_queue.get_nowait()
                        logger.info(f"Retrieved command: {cmd.get_description()}")
                        self._execute_command(cmd)
                    except queue.Empty:
                        pass
                
                # Check if current command is complete
                self._check_command_completion()
                
                # Always emit telemetry (outside locks)
                feedback = self.driver.get_feedback()
                self._emit_status(feedback)
                
            except Exception as e:
                logger.error(f"Error in motion service loop: {e}")
                self.current_state = "ERROR"
            
            time.sleep(dt)

    def _execute_command(self, cmd: Command):
        """Execute a command with proper error handling and no deadlocks."""
        if self.paused:
            logger.warning(f"Execution paused due to limit hit. Skipping command: {cmd.get_description()}")
            return
        
        # Check if we're already executing something
        with self._command_lock:
            if self._current_command is not None:
                logger.warning(f"Already executing a command. Skipping: {cmd.get_description()}")
                return
            
            # Set current command
            self._current_command = cmd
            self._command_start_time = time.time()
        
        # Update state
        self.current_state = "EXECUTING"
        
        try:
            logger.info(f"Executing: {cmd.get_description()}")
            # Execute command outside of locks to prevent deadlocks
            cmd.execute(self.driver)
            
            if isinstance(cmd, (GripperCommand, HomeCommand)):
                # Gripper and home commands have a 0.5 second delay to prevent overwhelming the servo
                pass  # Don't mark as complete immediately
                
        except Exception as e:
            logger.error(f"Error executing command {cmd.get_description()}: {e}")
            self.current_state = "ERROR"
            with self._command_lock:
                self._current_command = None
                
    def _check_command_completion(self):
        """Check if the current command has completed."""
        with self._command_lock:
            if self._current_command is not None:
                elapsed = time.time() - self._command_start_time
                
                if isinstance(self._current_command, JointCommand):
                    if elapsed >= self._current_command.duration_s:
                        logger.info(f"Joint command execution complete after {elapsed:.2f}s")
                        self._current_command = None
                        self.current_state = "IDLE"
                elif isinstance(self._current_command, (GripperCommand, HomeCommand)):
                    required_delay = self._current_command.delay if isinstance(self._current_command, GripperCommand) else 1.25
                    if elapsed >= required_delay:
                        logger.info(f"Gripper/Home command execution complete after {elapsed:.2f}s")
                        self._current_command = None
                        self.current_state = "IDLE"

    def _emit_status(self, feedback: Dict[str, Any]):
        """Emit status via WebSocket."""
        try:
            should_pause = self.driver.handle_limits(feedback)
            if should_pause:
                self.paused = True
                self.current_state = "LIMIT_HIT"

            # Get encoder values - prefer motor encoders if available, otherwise convert joint angles
            joint_angles = feedback.get("q", [])
            motor_encoders = feedback.get("motor_encoders")
            
            if motor_encoders is not None:
                encoders = motor_encoders
            else:
                # Fallback: convert joint angles to encoder values
                encoders = []
                can_driver = None
                if isinstance(self.driver, CanDriver):
                    can_driver = self.driver
                elif isinstance(self.driver, CompositeDriver):
                    for driver in self.driver.drivers:
                        if isinstance(driver, CanDriver):
                            can_driver = driver
                            break
                
                if can_driver is not None:
                    for i, angle in enumerate(joint_angles):
                        encoder_value = can_driver.angle_to_encoder(angle, i)
                        encoders.append(encoder_value)
                else:
                    # Fallback: use joint angles as-is if no CanDriver found
                    encoders = joint_angles.copy()

            event = {
                "state": self.current_state,
                "q": joint_angles,
                "encoders": encoders,
                "error": feedback.get("error", []),
                "limits": feedback.get("limits", [])
            }
            
            if self.ws_emit and (self.has_active_connections is None or self.has_active_connections()):
                self.ws_emit("telemetry", event)
        except Exception as e:
            logger.error(f"Error emitting status: {e}")

    def open_gripper(self):
        """Enqueue a command to open the gripper."""
        self._cancel_pending_gripper_commands()  # Cancel any pending gripper commands
        target_position = 1.0  # Fully open
        position_diff = abs(target_position - self._current_gripper_position)
        delay = max(position_diff * 0.5, 0.2)  # Reduced minimum delay from 0.75s to 0.2s
        cmd = GripperCommand('open', delay=delay)
        self.enqueue(cmd)
        self._current_gripper_position = target_position

    def close_gripper(self):
        """Enqueue a command to close the gripper."""
        self._cancel_pending_gripper_commands()  # Cancel any pending gripper commands
        target_position = 0.0  # Fully closed
        position_diff = abs(target_position - self._current_gripper_position)
        delay = max(position_diff * 0.5, 0.2)  # Reduced minimum delay from 0.75s to 0.2s
        cmd = GripperCommand('close', delay=delay)
        self.enqueue(cmd)
        self._current_gripper_position = target_position

    def set_gripper_position(self, position: float):
        """Enqueue a command to set the gripper position."""
        self._cancel_pending_gripper_commands()  # Cancel any pending gripper commands
        target_position = max(0.0, min(1.0, position))  # Clamp to 0.0-1.0
        position_diff = abs(target_position - self._current_gripper_position)
        delay = max(position_diff * 0.3, 0.05)  # Reduced minimum delay from 0.1s to 0.05s for smoother incremental control
        cmd = GripperCommand('set', position=target_position, delay=delay)
        self.enqueue(cmd)
        self._current_gripper_position = target_position


    def send_joint_targets(self, q: List[float], duration_s: float = 1.0):
        """Enqueue a joint movement command."""
        cmd = JointCommand(q, duration_s)
        self.enqueue(cmd)

    def home_joints(self, joint_indices: List[int]):
        """Enqueue a command to home specific joints."""
        cmd = HomeCommand(joint_indices)
        self.enqueue(cmd)

    def estop(self):
        """Emergency stop all motors immediately."""
        logger.warning("🚨 EMERGENCY STOP ACTIVATED")
        self.clear_queue()
        if hasattr(self.driver, 'estop'):
            self.driver.estop()
        self.current_state = "EMERGENCY_STOP"
        logger.warning("Emergency stop completed")