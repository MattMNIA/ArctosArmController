import logging
from typing import Protocol, List, Dict, Any
import platform
import time
import concurrent.futures
import can
import subprocess
import math
import yaml
from pathlib import Path
from typing import cast
from can import BusABC
from .mks_servo_can import mks_servo
from .mks_servo_can.mks_servo import Enable
from utils.config_manager import ConfigManager
import threading

logger = logging.getLogger(__name__)

class CanDriver():
    def __init__(self):
        # Load configuration
        config_path = Path(__file__).parent.parent.parent / "config" / "default.yml"
        self.config_manager = ConfigManager(config_path)
        self.coupled_mode = self.config_manager.get('coupled_axis_mode', False)
        self.gear_ratios = self.config_manager.get('can_driver.gear_ratios', [1.0] * 6)
        self.encoder_resolution = self.config_manager.get('can_driver.encoder_resolution', 16384)
        self.can_interface = self.config_manager.get('can_driver.can_interface', 'COM4')
        self.bitrate = self.config_manager.get('can_driver.bitrate', 500000)
        self.default_speed = self.config_manager.get('can_driver.default_speed', 500)
        self.default_acc = self.config_manager.get('can_driver.default_acc', 150)
        self.auto_clear_limits = self.config_manager.get('can_driver.auto_clear_limits', False)
        
        # Communication timeout settings
        self.can_timeout = self.config_manager.get('can_driver.can_timeout', 2.0)
        self.servo_timeout = self.config_manager.get('can_driver.servo_timeout', 1.0)
        
        self.bus = None
        self.servos = []
        
        # Use a reasonable thread pool size and add proper shutdown
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=6, 
            thread_name_prefix="can_driver"
        )
        self.pending_futures = []
        self.motion_service = None
        self.limit_hit = False
        self.previous_limits = [[False, False] for _ in range(6)]
        
        # Add locks for thread safety
        self._servo_lock = threading.RLock()  # Reentrant lock for servo operations
        self._futures_lock = threading.Lock()  # For managing futures list

    def is_can_interface_up(self) -> bool:
        """
        Checks if the specified CAN interface is active.
        """
        if platform.system() == "Windows":
            try:
                import serial.tools.list_ports
                ports = [port.device for port in serial.tools.list_ports.comports()]
                return self.can_interface in ports
            except ImportError:
                logger.warning("pyserial not available, assuming CAN interface is up")
                return True
        else:
            try:
                result = subprocess.run(
                    ["ip", "link", "show", self.can_interface], 
                    capture_output=True, 
                    text=True, 
                    timeout=5.0
                )
                return "UP" in result.stdout
            except (subprocess.TimeoutExpired, Exception) as e:
                logger.error(f"Error checking CAN interface: {e}")
                return False

    def angle_to_encoder(self, angle_rad: float, axis_index: int) -> int:  
        """
        Converts a joint angle from radians to an encoder value for a given axis.
        """
        if axis_index >= len(self.gear_ratios):
            logger.warning(f"Axis index {axis_index} out of range, using default gear ratio")
            gear_ratio = 1.0
        else:
            gear_ratio = self.gear_ratios[axis_index]
        
        encoder_value = int((angle_rad / (2 * math.pi)) * self.encoder_resolution * gear_ratio)
        return encoder_value

    def encoder_to_angle(self, encoder_value: int, axis_index: int) -> float:
        """
        Converts an encoder value to a joint angle in radians for a given axis.
        """
        if axis_index >= len(self.gear_ratios):
            logger.warning(f"Axis index {axis_index} out of range, using default gear ratio")
            gear_ratio = 1.0
        else:
            gear_ratio = self.gear_ratios[axis_index]
        
        angle_rad = (encoder_value / (self.encoder_resolution * gear_ratio)) * (2 * math.pi)
        return angle_rad
    
    def _read_encoder_with_fallback(self, i: int, servo) -> int:
        """Reads encoder value for a single axis with fallback to 0 on failure."""
        try:
            # Add timeout to prevent hanging
            with self._servo_lock:
                encoder_value = servo.read_encoder_value_addition()
                if encoder_value is None:
                    logger.warning(f"Failed to read encoder value for Axis {i}, setting to 0.")
                    return 0
                return encoder_value
        except Exception as e:
            logger.warning(f"Error reading encoder for Axis {i}: {e}")
            return 0
    
    def connect(self) -> None: 
        """
        Initializes the CAN bus interface with proper error handling.
        """
        if not self.is_can_interface_up():
            logger.warning(f"CAN interface is not available on {self.can_interface}.")
            self.bus = None
            return

        try:
            time.sleep(1)  # Delay to allow device to be ready
            if platform.system() == "Windows":
                self.bus = can.interface.Bus(
                    bustype="slcan", 
                    channel=self.can_interface, 
                    bitrate=self.bitrate,
                    timeout=self.can_timeout
                )
            else:
                self.bus = can.interface.Bus(
                    bustype="socketcan", 
                    channel=self.can_interface,
                    timeout=self.can_timeout
                )

            logger.info(f"CAN bus successfully initialized on {self.can_interface} with bitrate {self.bitrate}.")
        except Exception as e:
            logger.warning(f"CAN bus initialization failed: {e}")
            self.bus = None

    def enable(self) -> None:
        """
        Initializes the servo motors connected to the CAN bus with proper timeout handling.
        """
        if self.bus is None:
            raise RuntimeError("CAN bus not initialized. Call connect() first.")
        
        logger.info("🔧 Initializing servos...")
        start_time = time.time()

        try:
            notifier = can.Notifier(cast(BusABC, self.bus), [])
        except Exception as e:
            logger.error(f"❌ Failed to create CAN notifier: {e}")
            raise

        with self._servo_lock:
            for i in range(1, 7):
                try:
                    logger.debug(f"🔹 Creating servo instance for ID {i}")
                    servo = mks_servo.MksServo(self.bus, notifier, i)
                    
                    # Add timeout for servo initialization
                    servo.enable_motor(Enable.Enable)
                    self.servos.append(servo)
                    logger.debug(f"✅ Servo {i} initialized.")
                    
                    # Small delay between servo initializations
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to initialize servo ID {i}: {e}")
                    # Don't raise immediately, try to initialize other servos
                    continue

            if not self.servos:
                raise RuntimeError("No servos were successfully initialized")

            # Enable limit ports on servos 3–6 (Index 2 and above)
            for index, servo in enumerate(self.servos[2:], start=3):
                try:
                    logger.debug(f"🔸 Enabling limit port on Servo {index}")
                    servo.set_limit_port_remap(Enable.Enable)
                    time.sleep(0.1)
                    logger.debug(f"✅ Limit port enabled on Servo {index}")
                except Exception as e:
                    logger.error(f"⚠️ Failed to enable limit port on Servo {index}: {e}")

        duration = time.time() - start_time
        logger.info(f"✅ {len(self.servos)} servos initialized in {duration:.2f} seconds.")

    def disable(self) -> None:
        """
        Disables the servo motors connected to the CAN bus with proper cleanup.
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized.")
            return
        
        # Cancel all pending futures first
        self._cancel_pending_futures()
        
        with self._servo_lock:
            if not self.servos:
                logger.warning("No servos to disable.")
                return
            
            logger.info("🔧 Disabling servos...")
            start_time = time.time()

            try:
                notifier = can.Notifier(cast(BusABC, self.bus), [])
            except Exception as e:
                logger.error(f"❌ Failed to create CAN notifier: {e}")

            for i, servo in enumerate(self.servos, start=1):
                try:
                    logger.debug(f"🔹 Disabling servo ID {i}")
                    servo.disable_motor(Enable.Enable)
                    logger.debug(f"✅ Servo {i} disabled.")
                except Exception as e:
                    logger.warning(f"❌ Failed to disable servo ID {i}: {e}")
                    # Continue with other servos
                
            self.servos = []  # Clear the list after disabling
                
        duration = time.time() - start_time
        logger.info(f"✅ All servos disabled in {duration:.2f} seconds.")
        
        # Shutdown thread pool
        try:
            self.thread_pool.shutdown(wait=True)
            logger.info("Thread pool shut down successfully.")
        except Exception as e:
            logger.warning(f"Error shutting down thread pool: {e}")

    def home(self) -> None: 
        """Home all axes - to be implemented."""
        pass

    def send_joint_targets(self, q: List[float], t_s: float = 1.0):
        """
        Map MotionService send_joint_targets() to move_to_angles() with improved error handling.
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized. Call connect() first.")
            return
        
        with self._servo_lock:
            if not self.servos:
                logger.warning("Servos not enabled. Call enable() first.")
                return

        # Validate input
        if len(q) != 6:
            logger.error(f"Expected 6 joint angles, got {len(q)}")
            return

        # Default speed and acceleration
        default_speed = self.default_speed
        default_acc = self.default_acc
        
        angles_rad = list(q)
        
        # Handle coupled mode
        if self.coupled_mode and len(angles_rad) >= 6:
            b_axis = angles_rad[4] + angles_rad[5]
            c_axis = angles_rad[4] - angles_rad[5]
            angles_rad[4] = b_axis
            angles_rad[5] = c_axis

        # Internal move helper with timeout
        def _move_servo(i: int, angle_rad: float):
            try:
                encoder_val = self.angle_to_encoder(angle_rad, i)
                logger.debug(f"Axis {i}: {math.degrees(angle_rad):.2f}° -> enc {encoder_val}")
                
                with self._servo_lock:
                    if i >= len(self.servos):
                        logger.error(f"Servo index {i} out of range")
                        return False
                    
                    result = self.servos[i].run_motor_absolute_motion_by_axis(
                        default_speed, default_acc, encoder_val
                    )
                    
                    if result is None:
                        logger.warning(f"Failed to send command to servo {i+1}")
                        return False
                    
                    return True
                    
            except Exception as e:
                logger.error(f"Failed to send command to servo {i+1}: {e}")
                return False

        # Cancel previous pending futures
        self._cancel_pending_futures()

        # Submit new futures with error handling
        futures = []
        with self._futures_lock:
            try:
                for i, angle in enumerate(angles_rad):
                    if i >= len(self.servos):
                        logger.warning(f"Skipping axis {i}, no corresponding servo")
                        continue
                    
                    future = self.thread_pool.submit(_move_servo, i, angle)
                    futures.append(future)
                
                self.pending_futures = futures
                logger.info(f"Joint targets submitted to {len(futures)} servos")
                
            except RuntimeError as e:
                logger.error(f"Failed to submit servo commands: {e}")
                # Thread pool might be shut down
                return

    def _cancel_pending_futures(self):
        """Cancel all pending futures to prevent resource leaks."""
        with self._futures_lock:
            cancelled_count = 0
            for future in self.pending_futures:
                if not future.done():
                    future.cancel()
                    cancelled_count += 1
            
            if cancelled_count > 0:
                logger.debug(f"Cancelled {cancelled_count} pending futures")
            
            self.pending_futures = []

    def send_can_message_gripper(self, arbitration_id: int, data: List[int]) -> None:  
        """
        Sends a CAN message to control the gripper.

        This method sends a CAN message with the specified arbitration ID and data to control
        the gripper. It handles the message sending process and logs the sent message details.
        It includes a delay of 500 ms after sending the message to allow for processing.

        Args:
            arbitration_id (int): The arbitration ID of the CAN message.
            data (List[int]): A list of integers representing the data payload of the CAN message.

        Raises:
            can.CanError: If there is an issue sending the CAN message.
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized. Cannot send gripper command.")
            return
        
        try:
            msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
            self.bus.send(msg)
            data_bytes = ', '.join([f'0x{byte:02X}' for byte in msg.data])
            logger.debug(f"Sent CAN message: ID=0x{msg.arbitration_id:X}, Data=[{data_bytes}]")
            time.sleep(0.5)  # Delay of 500 ms to allow for processing
        except can.CanError as e:
            logger.error(f"Error sending CAN message: {e}")

    def _set_gripper_current(self, force: float) -> None:
        """
        Set the working current for gripper servos based on force parameter.
        
        Args:
            force (float): Force value
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized. Cannot set gripper current.")
            return
            
        try:
            # Convert force 0.0-1.0
            # Max current for most MKS servos is 3000 mA
            current_ma = min(int(force * 3000), 3000)
            current_ma = max(current_ma, 0)
            

            try:
                # Create servo instance for gripper servo
                gripper_servo = mks_servo.MksServo(self.bus, None, 7)
                gripper_servo.set_working_current(current_ma)
                logger.debug(f"Set gripper servo current to {current_ma} mA")
            except Exception as e:
                logger.warning(f"Failed to set current for gripper servo: {e}")
        except Exception as e:
            logger.error(f"Error setting gripper current: {e}")

    def open_gripper(self, force: float = 50.0) -> None: 
        """
        Opens the gripper with specified force.

        Args:
            force (float): Force

        Raises:
            Exception: If there is an issue sending the open gripper command.

        """
        try:
            self._set_gripper_current(force)
            self.send_can_message_gripper(0x07, [0xFF])
            logger.info(f"Gripper opened with force {force}N.")
        except Exception as e:
            logger.error(f"Error sending open gripper command: {e}")

    def close_gripper(self, force: float = 50.0) -> None: 
        """
        Closes the gripper with specified force.

        Args:
            force (float): Force

        Raises:
            Exception: If there is an issue sending the close gripper command.

        """
        try:
            self._set_gripper_current(force)
            self.send_can_message_gripper(0x07, [0x00])
            logger.info(f"Gripper closed with force {force}N.")
        except Exception as e:
            logger.error(f"Error sending close gripper command: {e}")

    def set_gripper_position(self, position: float, force: float = 50.0) -> None: 
        """
        Set gripper to specific opening width with specified force.

        Args:
            position (float): Position (0.0 = closed, 1.0 = open)
            force (float): Force
        """
        try:
            self._set_gripper_current(force)
            # Clamp position to valid range
            clamped_position = max(0.0, min(1.0, position))
            # Map 0.0-1.0 to 0x00-0xFF
            data_value = int(clamped_position * 255)
            self.send_can_message_gripper(0x07, [data_value])
            logger.info(f"Gripper set to position {clamped_position} with force {force}N.")
        except Exception as e:
            logger.error(f"Error sending set gripper position command: {e}")

    def grasp_object(self, force: float = 100.0) -> None:
        """
        Grasp object by closing the gripper with specified force.
        
        Args:
            force (float): Grasping force (higher = stronger grip)
        """
        self.close_gripper(force)

    def get_feedback(self) -> Dict[str, Any]:
        """Get robot feedback with improved error handling."""
        with self._servo_lock:
            if not self.servos:
                logger.warning("Servos not enabled.")
                return {"q": [], "dq": [], "error": [], "limits": []}
        
        q = []
        dq = []
        limits = []
        
        with self._servo_lock:
            # Read joint positions
            for i, servo in enumerate(self.servos):
                encoder_value = self._read_encoder_with_fallback(i, servo)
                angle_rad = self.encoder_to_angle(encoder_value, i)
                q.append(angle_rad)
            
            # Read joint velocities with error handling
            for i, servo in enumerate(self.servos):
                try:
                    speed = servo.read_motor_speed()
                    dq.append(speed if speed is not None else 0.0)
                except Exception as e:
                    logger.warning(f"Error reading speed for servo {i}: {e}")
                    dq.append(0.0)
            
            # Read limit switch status
            for i, servo in enumerate(self.servos):
                try:
                    status = servo.read_io_port_status()
                    if status is not None:
                        in1 = not bool(status & 0x01)  # Bit 0: IN_1
                        in2 = not bool((status >> 1) & 0x01)  # Bit 1: IN_2
                        limits.append([in1, in2])
                    else:
                        limits.append([False, False])
                except Exception as e:
                    logger.warning(f"Error reading IO status for servo {i}: {e}")
                    limits.append([False, False])
                    
            # Read shaft angle error for each servo
            error = []
            for i, servo in enumerate(self.servos):
                try:
                    err = servo.read_motor_shaft_angle_error()
                    error.append(err if err is not None else 0)
                except Exception as e:
                    logger.warning(f"Error reading shaft angle error for servo {i}: {e}")
                    error.append(0)

        return {"q": q, "dq": dq, "error": error, "limits": limits}

    def estop(self) -> None:
        """
        Immediately stops all motors by sending the emergency stop command to each servo.
        """
        logger.warning("🚨 EMERGENCY STOP ACTIVATED")
        
        # Cancel all pending operations
        self._cancel_pending_futures()
        
        with self._servo_lock:
            if not self.servos:
                logger.error("No servos initialized for emergency stop!")
                return
            
            for i, servo in enumerate(self.servos):
                try:
                    result = servo.emergency_stop_motor()
                    logger.debug(f"Emergency stop sent to servo {i+1}: {result}")
                except Exception as e:
                    logger.error(f"Failed to send emergency stop to servo {i+1}: {e}")

    def handle_limits(self, feedback: Dict[str, Any]) -> bool:
        """
        Handle limit switches based on feedback.
        Returns True if execution should be paused due to uncleared limits.
        """
        limits = feedback.get("limits", [])
        dq = feedback.get("dq", [])
        
        if len(limits) != len(dq):
            logger.warning("Mismatch between limits and velocity feedback lengths")
            return False
        
        # Check if any servo is at limit and stopped
        limit_hit = False
        for i, (lim, vel) in enumerate(zip(limits, dq)):
            # Check if any limit is hit (assuming False means limit hit)
            if (len(lim) >= 2 and any(lim)) and abs(vel) < 1e-6:
                logger.warning(f"Limit hit on axis {i}: {lim}, velocity: {vel}")
                limit_hit = True
                break
        
        if limit_hit:
            if not self.limit_hit:
                self.limit_hit = True
                logger.warning("Limit switch detected, clearing motion queue")
                if self.motion_service:
                    self.motion_service.clear_queue()
                
                # Cancel any ongoing movements
                self._cancel_pending_futures()
            
            if self.auto_clear_limits:
                logger.info("Auto-clearing limits enabled. Attempting to clear limits automatically.")
                try:
                    cleared = self.clear_limits()
                    if cleared:
                        logger.info("Limits cleared successfully.")
                        self.limit_hit = False
                        return False
                    else:
                        logger.error("Failed to clear limits automatically.")
                        return True
                except Exception as e:
                    logger.error(f"Error during auto-clear limits: {e}")
                    return True
            else:
                logger.error("Limit switch hit and joint stopped. Execution paused.")
                return True
        else:
            if self.limit_hit:
                logger.info("Limits cleared, resuming normal operation")
                self.limit_hit = False
            return False

    def clear_limits(self) -> bool:
        """
        Attempt to move servos away from hit limits with improved safety and error handling.
        """
        with self._servo_lock:
            if not self.servos:
                logger.error("No servos available for limit clearing")
                return False
        
        feedback = self.get_feedback()
        logger.debug(f"Limit clearing feedback: {feedback}")
        limits = feedback.get("limits", [])
        q = feedback.get("q", [])
        
        if not limits or not q:
            logger.error("No feedback available for limit clearing")
            return False
        
        delta = math.radians(1)  # 1 degree in radians
        max_attempts = 10
        success = True
        
        for i, lim in enumerate(limits):
            if len(lim) < 2 or not any(lim):  # No limit hit or invalid data
                continue
            
            # Determine direction to move away from limit
            # Assuming lim[0] is min limit, lim[1] is max limit
            if not lim[0]:  # Min limit hit
                direction = 1  # Move positive
            elif not lim[1]:  # Max limit hit
                direction = -1  # Move negative
            else:
                continue  # No limit hit
            
            attempts = 0
            current_angle = q[i]
            
            logger.info(f"Attempting to clear limit on servo {i+1} (direction: {direction})")
            
            while attempts < max_attempts:
                new_angle = current_angle + direction * delta
                logger.debug(f"Clearing limit on servo {i+1}, attempt {attempts+1}, moving to {math.degrees(new_angle):.2f}°")
                
                try:
                    encoder_val = self.angle_to_encoder(new_angle, i)
                    logger.debug(f"Servo {i+1}: Moving to encoder value {encoder_val}")
                    with self._servo_lock:
                        if i >= len(self.servos):
                            logger.error(f"Servo index {i} out of range during limit clearing")
                            success = False
                            break
                            
                        result = self.servos[i].run_motor_absolute_motion_by_axis(
                            self.default_speed // 2,  # Use slower speed for safety
                            self.default_acc // 2,    # Use slower acceleration
                            encoder_val
                        )
                        
                        if result is None:
                            logger.error(f"Failed to send clear command to servo {i+1}")
                            success = False
                            break
                    
                    # Wait for movement with timeout
                    time.sleep(0.5)
                    current_angle = new_angle
                    
                except Exception as e:
                    logger.error(f"Error clearing limit on servo {i+1}: {e}")
                    success = False
                    break
                
                # Re-check this servo's limit status
                try:
                    time.sleep(0.1)
                    new_feedback = self.get_feedback()
                    new_limits = new_feedback.get("limits", [])
                    
                    if (i < len(new_limits) and len(new_limits[i]) >= 2 and 
                        not any(new_limits[i])):  # Limit cleared
                        logger.info(f"Limit cleared on servo {i+1} after {attempts+1} attempts")
                        break
                        
                except Exception as e:
                    logger.error(f"Error checking limit status for servo {i+1}: {e}")
                    success = False
                    break
                
                attempts += 1
            else:
                logger.warning(f"Failed to clear limit on servo {i+1} after {max_attempts} attempts")
                success = False
        
        # Final verification
        if success:
            time.sleep(0.2)  # Allow time for final status update
            final_feedback = self.get_feedback()
            final_limits = final_feedback.get("limits", [])
            
            # Check if any limits are still hit
            still_hit = any(
                not any(lim) for lim in final_limits 
                if len(lim) >= 2
            )
            
            if not still_hit:
                self.limit_hit = False
                logger.info("All limits successfully cleared")
                return True
            else:
                logger.warning("Some limits still active after clearing attempt")
                return False
        
        return False

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self._cancel_pending_futures()
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=False)
        except Exception:
            pass  # Ignore cleanup errors