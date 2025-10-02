import threading
import time
import queue
import math
from dataclasses import dataclass
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
    def __init__(self, q: List[float], duration_s: Optional[float] = None):
        self.q = q
        self.duration_s = duration_s

    def execute(self, driver) -> None:
        """Start the joint movement (non-blocking)."""
        if self.duration_s is None:
            driver.send_joint_targets(self.q)
        else:
            driver.send_joint_targets(self.q, self.duration_s)

    def get_description(self) -> str:
        if self.duration_s is None:
            return f"Joint move: q={self.q}, adaptive duration"
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


@dataclass
class ActiveCommandContext:
    command: Command
    start_time: float
    min_duration: float
    timeout: float
    target_q: Optional[List[float]] = None
    target_gripper: Optional[float] = None
    tolerance: float = 0.02
    velocity_tolerance: float = 0.05
    complete_on_return: bool = False

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
        self._active_context: Optional[ActiveCommandContext] = None
        self._position_tolerance = 0.02  # radians (~1.1 degrees)
        self._velocity_tolerance = 0.05  # rad/s
        self._min_joint_timeout = 3.0
        self._joint_timeout_scale = 2.5

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
            self.current_state = "RUNNING"
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
                
                # Always emit telemetry (outside locks)
                feedback = self.driver.get_feedback()
                self._handle_feedback(feedback)
                
            except Exception as e:
                logger.error(f"Error in motion service loop: {e}")
                self.current_state = "ERROR"
            
            time.sleep(dt)

    def _execute_command(self, cmd: Command):
        """Execute a command with proper error handling and no deadlocks."""
        if self.paused:
            logger.warning(f"Execution paused due to limit hit. Skipping command: {cmd.get_description()}")
            return
        
        start_time = time.time()
        context = self._build_context_for_command(cmd, start_time)
        context.tolerance = self._position_tolerance
        context.velocity_tolerance = self._velocity_tolerance
        
        # Check if we're already executing something
        with self._command_lock:
            if self._current_command is not None:
                logger.warning(f"Already executing a command. Skipping: {cmd.get_description()}")
                return
            
            # Set current command
            self._current_command = cmd
            self._command_start_time = start_time
            self._active_context = context
        
        # Update state
        self.current_state = "EXECUTING"
        
        try:
            logger.info(f"Executing: {cmd.get_description()}")
            # Execute command outside of locks to prevent deadlocks
            cmd.execute(self.driver)
            
            if context.complete_on_return:
                self._complete_current_command(new_state="IDLE")
        except Exception as e:
            logger.error(f"Error executing command {cmd.get_description()}: {e}")
            self._abort_current_command(f"Error executing command {cmd.get_description()} : {e}", new_state="ERROR")

    def _build_context_for_command(self, cmd: Command, start_time: float) -> ActiveCommandContext:
        if isinstance(cmd, JointCommand):
            target_q = list(cmd.q)
            estimated_time = self._estimate_joint_motion_time(target_q)
            base_time = cmd.duration_s if cmd.duration_s is not None else estimated_time
            base_time = max(base_time, 0.1)
            min_duration = max(0.1, min(base_time * 0.5, base_time))
            timeout = (base_time * self._joint_timeout_scale) + 1.0
            timeout = max(timeout, self._min_joint_timeout, min_duration + 1.0)
            return ActiveCommandContext(
                command=cmd,
                start_time=start_time,
                min_duration=min_duration,
                timeout=timeout,
                target_q=target_q
            )
        if isinstance(cmd, GripperCommand):
            min_duration = max(cmd.delay, 0.1)
            timeout = min_duration + 1.0
            if cmd.action == 'set' and cmd.position is not None:
                target_gripper = cmd.position
            elif cmd.action == 'open':
                target_gripper = 1.0
            elif cmd.action == 'close':
                target_gripper = 0.0
            else:
                target_gripper = None
            return ActiveCommandContext(
                command=cmd,
                start_time=start_time,
                min_duration=min_duration,
                timeout=timeout,
                target_gripper=target_gripper
            )
        if isinstance(cmd, HomeCommand):
            return ActiveCommandContext(
                command=cmd,
                start_time=start_time,
                min_duration=0.0,
                timeout=90.0,
                complete_on_return=True
            )
        return ActiveCommandContext(
            command=cmd,
            start_time=start_time,
            min_duration=0.1,
            timeout=self._min_joint_timeout
        )

    def _complete_current_command(self, new_state: str = "IDLE") -> None:
        with self._command_lock:
            if self._current_command is None:
                return
            description = self._current_command.get_description()
            self._current_command = None
            self._active_context = None
        self.current_state = new_state
        logger.info(f"Completed command: {description}")

    def _abort_current_command(self, reason: str, new_state: Optional[str] = None) -> None:
        with self._command_lock:
            if self._current_command is None:
                return
            description = self._current_command.get_description()
            self._current_command = None
            self._active_context = None
        logger.warning(f"Aborting command '{description}': {reason}")
        if new_state:
            self.current_state = new_state

    def _check_command_completion(self, feedback: Dict[str, Any]):
        """Check if the current command has completed using feedback and timing."""
        with self._command_lock:
            context = self._active_context
        
        if context is None or context.complete_on_return:
            return

        elapsed = time.time() - context.start_time

        if elapsed > context.timeout:
            self._abort_current_command(
                f"Command timeout after {elapsed:.2f}s (limit {context.timeout:.2f}s)",
                new_state="TIMEOUT"
            )
            self.paused = True
            return

        if isinstance(context.command, JointCommand):
            joint_feedback = feedback.get("q", [])
            velocities = feedback.get("dq", [])
            target = context.target_q or []

            if not joint_feedback or not target:
                return

            paired = list(zip(target, joint_feedback))
            if not paired:
                return

            position_error = max(abs(t - q) for t, q in paired)
            velocity_samples = velocities[:len(paired)] if velocities else []
            max_velocity = max(abs(v) for v in velocity_samples) if velocity_samples else 0.0

            if (
                elapsed >= context.min_duration and
                position_error <= context.tolerance and
                max_velocity <= context.velocity_tolerance
            ):
                logger.info(
                    "Joint command complete: max_error=%.4f rad, max_velocity=%.4f rad/s, elapsed=%.2fs",
                    position_error,
                    max_velocity,
                    elapsed
                )
                self._complete_current_command()
        elif isinstance(context.command, GripperCommand):
            if elapsed >= context.min_duration:
                logger.info(
                    "Gripper command complete after %.2fs",
                    elapsed
                )
                self._complete_current_command()

    def _emit_status(self, feedback: Dict[str, Any]):
        """Emit status via WebSocket."""
        try:
            should_pause = self.driver.handle_limits(feedback)
            if should_pause:
                if not self.paused:
                    logger.warning("Pausing motion due to limit hit reported by driver")
                self.paused = True
                self._abort_current_command("Limit switch triggered", new_state="LIMIT_HIT")

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
                "limits": feedback.get("limits", []),
                "gripper_position": self._current_gripper_position
            }
            
            if self.ws_emit and (self.has_active_connections is None or self.has_active_connections()):
                self.ws_emit("telemetry", event)
        except Exception as e:
            logger.error(f"Error emitting status: {e}")

    def _handle_feedback(self, feedback: Dict[str, Any]):
        if feedback is None:
            return
        self._emit_status(feedback)
        self._check_command_completion(feedback)

    def _estimate_joint_motion_time(self, target_q: List[float]) -> float:
        try:
            feedback = self.driver.get_feedback() or {}
        except Exception as e:
            logger.debug(f"Unable to query feedback for timing estimate: {e}")
            feedback = {}

        current_q = feedback.get("q", [])
        joint_speeds = self._infer_joint_speed_limits(len(target_q))

        deltas: List[float] = []
        paired_len = min(len(current_q), len(target_q))
        for i in range(paired_len):
            deltas.append(abs(target_q[i] - current_q[i]))
        for i in range(paired_len, len(target_q)):
            deltas.append(abs(target_q[i]))

        times: List[float] = []
        for idx, delta in enumerate(deltas):
            speed = joint_speeds[idx] if idx < len(joint_speeds) else None
            if speed is None or speed <= 0:
                continue
            times.append(delta / speed if speed > 0 else 0.0)

        if not times:
            logger.debug("Unable to infer joint timings from configuration; using minimum timeout")
            return max(self._min_joint_timeout, 0.5)

        estimated = max(times)
        return max(estimated, 0.1)

    def _infer_joint_speed_limits(self, num_joints: int) -> List[Optional[float]]:
        can_driver = self._extract_can_driver()
        if can_driver is None:
            return [None] * num_joints

        try:
            motor_configs = can_driver.config_manager.get('can_driver.motors', [])
        except Exception as e:
            logger.warning(f"Failed to load motor configs for speed inference: {e}")
            motor_configs = []

        speed_map = {mc['id']: mc.get('speed_rpm') for mc in motor_configs if isinstance(mc, dict) and 'id' in mc}

        limits: List[Optional[float]] = []
        for joint_idx in range(num_joints):
            candidates: List[float] = []
            mapping: Dict[int, float] = {}
            try:
                mapping = can_driver.joint_velocity_to_motors(joint_idx, 1.0)
            except Exception as e:
                logger.debug(f"Failed to map joint {joint_idx} to motors for speed inference: {e}")

            if not mapping:
                speed_rpm = speed_map.get(joint_idx)
                limits.append(self._rpm_to_rad_s(speed_rpm))
                continue

            for motor_id, scale in mapping.items():
                speed_rpm = speed_map.get(motor_id)
                if speed_rpm is None or speed_rpm <= 0:
                    continue
                rad_s = self._rpm_to_rad_s(speed_rpm)
                if rad_s is None:
                    continue
                scale_mag = abs(scale) if scale is not None else 0.0
                if scale_mag <= 0:
                    continue
                candidates.append(rad_s / scale_mag)

            limits.append(min(candidates) if candidates else None)

        return limits

    def _extract_can_driver(self) -> Optional[CanDriver]:
        if isinstance(self.driver, CanDriver):
            return self.driver
        if isinstance(self.driver, CompositeDriver):
            for drv in self.driver.drivers:
                if isinstance(drv, CanDriver):
                    return drv
        return None

    @staticmethod
    def _rpm_to_rad_s(speed_rpm: Optional[float]) -> Optional[float]:
        if speed_rpm is None:
            return None
        return (speed_rpm * 2 * math.pi) / 60.0

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


    def send_joint_targets(self, q: List[float], duration_s: Optional[float] = None):
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
        self._abort_current_command("Emergency stop invoked")
        if hasattr(self.driver, 'estop'):
            self.driver.estop()
        self.current_state = "EMERGENCY_STOP"
        logger.warning("Emergency stop completed")