import logging
from typing import Protocol, List, Dict, Any, Optional
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

from .mks_servo_can.mks_enums import EnableStatus, Direction, EndStopLevel
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
        self.gear_ratios = self.config_manager.get('can_driver.gear_ratios', [1.0] * 6)
        self.encoder_resolution = self.config_manager.get('can_driver.encoder_resolution', 16384)
        self.can_interface = self.config_manager.get('can_driver.can_interface', 'COM4')
        self.bitrate = self.config_manager.get('can_driver.bitrate', 500000)
        
        # Load motor configurations
        motor_configs = self.config_manager.get('can_driver.motors', [])
        self.motor_configs = {}
        for mc in motor_configs:
            self.motor_configs[mc['id']] = {
                'speed_rpm': mc['speed_rpm'],
                'acceleration': mc['acceleration'],
                'homing_offset': mc.get('homing_offset', 0),
                'home_direction': mc.get('home_direction', 'CCW'),
                'home_speed': mc.get('home_speed', 50),
                'offset_speed': mc.get('offset_speed', 100),
                'endstop_level': mc.get('endstop_level', 'Low')
            }        # Fallback defaults for motors without config
        self.default_speed = 200
        self.default_acc = 50
        
        # Communication timeout settings
        self.can_timeout = self.config_manager.get('can_driver.can_timeout', 2.0)
        self.servo_timeout = self.config_manager.get('can_driver.servo_timeout', 0.1)
        
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
        self.current_limits = [[False, False] for _ in range(6)]  # Current endstop status
        self.velocity_direction = [None] * 6  # type: List[Optional[str]]  # Track velocity direction for each motor
        
        # Add locks for thread safety
        self._servo_lock = threading.RLock()  # Reentrant lock for servo operations
        self._futures_lock = threading.Lock()  # For managing futures list
        self.velocity_active = [False] * 6  # Track which joints have active velocity control

    def get_motor_config(self, motor_id: int) -> dict:
        """Get speed, acceleration, and homing config for a motor."""
        return self.motor_configs.get(motor_id, {
            'speed_rpm': self.default_speed,
            'acceleration': self.default_acc,
            'homing_offset': 0,
            'home_direction': 'CCW',
            'home_speed': 50,
            'offset_speed': 100,
            'endstop_level': 'Low'
        })

    def is_movement_allowed(self, motor_id: int, direction: str) -> bool:
        """
        Check if movement in given direction is allowed for motor, considering coupled constraints.
        
        For coupled motors 4 and 5:
        - When motor 4 (5) hits Low endstop, motor 5 (4) cannot move CCW
        - When motor 4 (5) hits High endstop, motor 5 (4) cannot move CW
        
        Args:
            motor_id: Motor ID (0-5)
            direction: 'CW' or 'CCW'
            
        Returns:
            True if movement is allowed, False otherwise
        """
        if motor_id not in [4, 5]:
            return True  # No coupling constraints for other motors
        
        # Determine coupled motor
        coupled_motor = 5 if motor_id == 4 else 4
        
        # Endstop mapping is different for each motor
        if coupled_motor == 4:  # Motor 5
            low_endstop_hit = self.current_limits[coupled_motor][1]   # Low endstop
            high_endstop_hit = self.current_limits[coupled_motor][0]  # High endstop
        else:  # coupled_motor == 5, Motor 6
            low_endstop_hit = self.current_limits[coupled_motor][0]   # Low endstop (opposite)
            high_endstop_hit = self.current_limits[coupled_motor][1]  # High endstop (opposite)
        
        if direction == 'CCW' and low_endstop_hit:
            return False  # Coupled motor's low endstop hit, cannot move CCW
        elif direction == 'CW' and high_endstop_hit:
            return False  # Coupled motor's high endstop hit, cannot move CW
        
        return True

    def check_and_enforce_coupled_limits(self) -> None:
        """
        Check for newly hit coupled endstops and stop affected motors to enforce coupling constraints.
        Also, if either limit is hit, set their value in the self.velocity_active and self.velocity_direction arrays to 0/None.
        """
        for motor_id in [4, 5]:
            coupled_motor = 5 if motor_id == 4 else 4

            # Get the correct endstop indices for this motor
            if motor_id == 4:  # Motor 5
                low_idx, high_idx = 1, 0
            else:  # motor_id == 5, Motor 6
                low_idx, high_idx = 0, 1

            # Check if low endstop was newly hit
            if (self.current_limits[motor_id][low_idx] and 
            not self.previous_limits[motor_id][low_idx]):
                # Low endstop newly hit on motor_id, stop coupled_motor from moving CCW
                logger.warning(f"Motor {motor_id} low endstop hit, stopping motor {coupled_motor} CCW movement")
                self._stop_motor_if_moving_direction(coupled_motor, 'CCW')
                # Set velocity state to stopped for both motors
                self.velocity_active[motor_id] = False
                self.velocity_direction[motor_id] = None
                self.velocity_active[coupled_motor] = False
                self.velocity_direction[coupled_motor] = None

            # Check if high endstop was newly hit
            if (self.current_limits[motor_id][high_idx] and 
            not self.previous_limits[motor_id][high_idx]):
                # High endstop newly hit on motor_id, stop coupled_motor from moving CW
                logger.warning(f"Motor {motor_id} high endstop hit, stopping motor {coupled_motor} CW movement")
                self._stop_motor_if_moving_direction(coupled_motor, 'CW')
                # Set velocity state to stopped for both motors
                self.velocity_active[motor_id] = False
                self.velocity_direction[motor_id] = None
                self.velocity_active[coupled_motor] = False
                self.velocity_direction[coupled_motor] = None

        # Update previous limits for next check
        self.previous_limits = [limit[:] for limit in self.current_limits]

    def _stop_motor_if_moving_direction(self, motor_id: int, direction: str) -> None:
        """
        Stop a motor if it's currently moving in the specified direction.
        
        Args:
            motor_id: Motor ID (0-5)
            direction: 'CW' or 'CCW'
        """
        if motor_id >= len(self.servos) or self.servos[motor_id] is None:
            return
        
        try:
            # Check if motor is in velocity mode and moving in the forbidden direction
            if (self.velocity_active[motor_id] and 
                self.velocity_direction[motor_id] == direction):
                logger.info(f"Stopping motor {motor_id} velocity control in {direction} direction")
                self.servos[motor_id].stop_motor_in_speed_mode(255)
                self.velocity_active[motor_id] = False
                self.velocity_direction[motor_id] = None
            
            # Also check if motor is running absolute motion (harder to stop mid-motion)
            # For now, we'll rely on the hardware endstops and velocity prevention
            # If needed, we could add emergency stop here, but that might be too aggressive
            
        except Exception as e:
            logger.error(f"Error stopping motor {motor_id}: {e}")

    def joints_to_motors(self, joint_angles: List[float]) -> Dict[int, float]:
        """
        Transform joint angles to motor angles, handling coupled axes.
        
        For coupled mode (joints 4 & 5):
        - Joint 4: motors move in opposite directions
        - Joint 5: motors move in the same direction
        
        Motor4 = Joint4 + Joint5
        Motor5 = -Joint4 + Joint5
        
        Args:
            joint_angles: List of 6 joint angles in radians
            
        Returns:
            Dict mapping motor_id to target angle in radians
        """
        coupled_mode = self.config_manager.get('joints.coupled_mode', False)
        
        if not coupled_mode or len(joint_angles) < 6:
            # Direct mapping: joint i -> motor i
            return {i: angle for i, angle in enumerate(joint_angles)}
        
        # Coupled mode for joints 4 and 5
        motor_angles = {}
        for i in range(6):
            if i < 4:
                # Joints 0-3: direct mapping
                motor_angles[i] = joint_angles[i]
            else:
                # Joints 4-5: coupled to motors 4-5
                q4 = joint_angles[4] if 4 < len(joint_angles) else 0
                q5 = joint_angles[5] if 5 < len(joint_angles) else 0
                motor_angles[4] = q4 + q5  # Motor 4
                motor_angles[5] = -q4 + q5  # Motor 5 (changed from q4 - q5)
                break  # Only need to do this once for both joints
        
        # Apply direction inversion for joints 1, 2, 4, 5 (motors 1, 2, 4, 5)
        for motor_id in motor_angles:
            if motor_id in [1, 2, 4, 5]:
                motor_angles[motor_id] = -motor_angles[motor_id]
        
        return motor_angles

    def joint_velocity_to_motors(self, joint_index: int, scale: float) -> Dict[int, float]:
        """
        Transform joint velocity scale commands to motor velocity scale commands.
        
        For coupled mode:
        - Joint 4: motors move in opposite directions
        - Joint 5: motors move in the same direction
        
        Args:
            joint_index: Joint index (0-5)
            scale: Joint velocity scale from -1.0 to 1.0
            
        Returns:
            Dict mapping motor_id to motor velocity scale
        """
        coupled_mode = self.config_manager.get('joints.coupled_mode', False)
        
        if not coupled_mode or joint_index < 4:
            # Direct mapping: joint i -> motor i
            return {joint_index: scale}
        
        # Coupled mode for joints 4 and 5
        if joint_index == 4:
            # Joint 4: motors opposite directions
            motor_scales = {4: scale, 5: -scale}
        elif joint_index == 5:
            # Joint 5: motors same direction
            motor_scales = {4: scale, 5: scale}
        else:
            motor_scales = {}
        
        # Apply direction inversion for joints 1, 2, 4, 5 (motors 1, 2, 4, 5)
        for motor_id in motor_scales:
            if motor_id in [1, 2, 4, 5]:
                motor_scales[motor_id] = -motor_scales[motor_id]
        
        return motor_scales

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
        
        # Recreate thread pool if it was shut down
        if hasattr(self, 'thread_pool') and self.thread_pool is not None:
            # Check if thread pool is shut down
            if self.thread_pool._shutdown:
                logger.info("Recreating thread pool after shutdown")
                self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=6, 
                    thread_name_prefix="can_driver"
                )
        elif not hasattr(self, 'thread_pool') or self.thread_pool is None:
            # Thread pool doesn't exist, create it
            self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=6, 
                thread_name_prefix="can_driver"
            )
        
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
                    
                    # Check enable status with retry
                    max_retries = 3
                    for attempt in range(max_retries):
                        status = servo.read_en_pins_status()
                        logger.debug(f"Servo {i} enable status (attempt {attempt+1}): {status}")
                        
                        # Check if endstop is triggered
                        try:
                            io_status = servo.read_io_port_status()
                            endstop_triggered = io_status is not None and (io_status & 1 or io_status & 2)
                        except Exception as e:
                            logger.debug(f"Could not read IO status for servo {i}: {e}")
                            endstop_triggered = False
                        
                        if status == EnableStatus.Enabled or endstop_triggered:
                            logger.debug(f"Servo {i} considered enabled (status: {status}, endstop_triggered: {endstop_triggered})")
                            break
                        elif attempt < max_retries - 1:
                            logger.warning(f"Servo {i} not enabled, retrying... (attempt {attempt+1}/{max_retries})")
                            time.sleep(0.5)  # Wait before retry
                        else:
                            # Final attempt failed, log detailed status
                            logger.error(f"Servo {i} failed to enable after {max_retries} attempts")
                            logger.error(f"Final status: {status}, endstop_triggered: {endstop_triggered}")
                            
                            # Check if endstop might be the issue
                            try:
                                io_status = servo.read_io_port_status()
                                logger.error(f"Servo {i} IO port status: {io_status} (bit 0=IN1, bit 1=IN2)")
                            except Exception as e:
                                logger.error(f"Could not read IO status for servo {i}: {e}")
                            
                            raise RuntimeError(f"Failed to enable servo ID {i} - status: {status}")
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
        for i, servo in enumerate(self.servos, start=1):
            try:
                status = servo.read_en_pins_status()
                # Check if endstop is triggered
                try:
                    io_status = servo.read_io_port_status()
                    endstop_triggered = io_status is not None and (io_status & 1 or io_status & 2)
                except Exception as e:
                    logger.debug(f"Could not read IO status for servo {i}: {e}")
                    endstop_triggered = False
                
                if status is not EnableStatus.Enabled and not endstop_triggered:
                    raise RuntimeError(f"Failed to enable servo ID {i} - status: {status}, endstop_triggered: {endstop_triggered}")
            except Exception as e:
                logger.error(f"Error checking enable status for servo ID {i}: {e}")
                raise
        duration = time.time() - start_time
        logger.info(f"✅ {len(self.servos)} servos initialized in {duration:.2f} seconds.")

    def disable(self) -> None:
        """
        Disables the servo motors connected to the CAN bus with proper cleanup.
        """
        #FIXME Fix disable error handling
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
        """Home all axes using configured homing parameters."""
        # Home all joints (0-5)
        self.home_joints(list(range(len(self.servos))))

    def home_joints(self, joint_indices: List[int]) -> None:
        """Home specific joints using the configured homing parameters.
        
        Joints 4 and 5 (motors 5 and 6) require special homing procedures:
        - If both joint 4 and 5 are selected, they are homed together with a full sequence
        - If only one is selected, it uses a partial sequence specific to that joint
        - Other joints (0-3) are homed with standard procedures
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized. Call connect() first.")
            return
        
        with self._servo_lock:
            if not self.servos:
                logger.warning("Servos not enabled. Call enable() first.")
                return

        # Cancel any pending futures before starting homing
        self._cancel_pending_futures()
        
        # Special handling for end effector joints (4 and 5)
        joint_4_selected = 4 in joint_indices
        joint_5_selected = 5 in joint_indices
        
        # Extract standard joints (0-3) to home concurrently
        standard_joints = [idx for idx in joint_indices if idx < 4]
        
        # Create a list of futures to track all homing tasks
        futures = []
        
        with self._futures_lock:
            # Recreate thread pool if it's shut down
            if self.thread_pool._shutdown:
                logger.info("Thread pool was shut down, recreating for homing")
                self.thread_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=6, 
                    thread_name_prefix="can_driver"
                )
            
            try:
                # Submit standard joints (0-3) for concurrent homing
                for joint_idx in standard_joints:
                    if joint_idx < 0 or joint_idx >= len(self.servos):
                        logger.error(f"Invalid joint index {joint_idx}, must be between 0 and {len(self.servos)-1}")
                        continue
                    future = self.thread_pool.submit(self._home_standard_joint, joint_idx)
                    futures.append(future)
                
                # Handle end effector joints (4-5)
                if joint_4_selected and joint_5_selected:
                    # Both joints selected - do full sequence
                    logger.info("Both joints 4 and 5 selected - running full coordinated homing sequence")
                    future = self.thread_pool.submit(self._home_motors_5_and_6)
                    futures.append(future)
                elif joint_4_selected:
                    # Only joint 4 - do opposite directions homing
                    logger.info("Joint 4 selected - running joint 4 specific homing")
                    future = self.thread_pool.submit(self._home_coupled_joint, 4)
                    futures.append(future)
                elif joint_5_selected:
                    # Only joint 5 - do same direction homing
                    logger.info("Joint 5 selected - running joint 5 specific homing")
                    future = self.thread_pool.submit(self._home_coupled_joint, 5)
                    futures.append(future)
                
                self.pending_futures = futures
                logger.info(f"Homing tasks submitted for {len(joint_indices)} joints")
                
            except RuntimeError as e:
                logger.error(f"Failed to submit homing tasks: {e}")
                return
        
        # Wait for all homing tasks to complete
        try:
            # Wait for all futures to complete with a reasonable timeout
            timeout_per_joint = 30.0  # 30 seconds per joint
            total_timeout = timeout_per_joint * len(futures)
            
            for future in futures:
                try:
                    future.result(timeout=total_timeout)
                except Exception as e:
                    logger.error(f"Homing task failed: {e}")
                    
        except Exception as e:
            logger.error(f"Error waiting for homing tasks: {e}")
        logger.info(f"Homing completed for {len(joint_indices)} joints")

    def _home_standard_joint(self, joint_idx: int) -> None:
        """Home a standard joint (0-3) using built-in servo homing.
        
        This method is used for joints 0-3 which use standard homing procedures.
        """
        servo = self.servos[joint_idx]
        motor_config = self.get_motor_config(joint_idx)
        
        try:
            logger.info(f"Homing joint {joint_idx} using standard method")
            
            # Use standard homing for motors 0-3
            servo.b_go_home()
            while servo.is_motor_running():
                time.sleep(0.05)
            
            # Apply homing offset if configured
            homing_offset = motor_config.get("homing_offset", 0)
            if homing_offset != 0:
                offset_speed = motor_config.get("offset_speed", 50)
                logger.info(f"Applying homing offset {homing_offset} to joint {joint_idx}")
                servo.run_motor_relative_motion_by_axis(offset_speed, 150, int(homing_offset))
                while servo.is_motor_running():
                    time.sleep(0.05)
            
            servo.set_current_axis_to_zero()
            logger.info(f"Successfully homed joint {joint_idx}")
            
        except Exception as e:
            logger.error(f"Failed to home joint {joint_idx}: {e}")
            raise
    def _home_coupled_joint(self, joint_idx: int) -> None:
        """Home a coupled joint (4 or 5) using their specific homing method.
        
        For joint 4, it runs opposite-direction homing sequence.
        For joint 5, it runs same-direction homing sequence.
        
        Args:
            joint_idx: Joint index (4 or 5)
        """
        if joint_idx == 4:
            self._home_joint_4_opposite_directions()
        elif joint_idx == 5:
            self._home_joint_5_same_direction()
        else:
            logger.error(f"Invalid joint index {joint_idx} for coupled homing")
            raise ValueError(f"Invalid joint index {joint_idx} for coupled homing")

    def _home_joint_4_opposite_directions(self) -> None:
        """Homing sequence for joint 4 (motor 5) - Opposite directions strategy.
        
        This homes joint 4 by moving motors 5 and 6 in opposite directions until motor 5's endstop is hit.
        """
        logger.info("Homing joint 4 using opposite-directions method")
        
        # Get servo instances
        servo5 = self.servos[4]  # Motor 5 (joint index 4)
        servo6 = self.servos[5]  # Motor 6 (joint index 5)
        
        # Get motor configurations
        config5 = self.get_motor_config(4)  # Motor 5
        config6 = self.get_motor_config(5)  # Motor 6
        
        # Get homing parameters 
        offset5 = config5.get("homing_offset", 25000)
        logger.info(f"offset5: {offset5}")
        
        # Get homing speeds and directions from motor configs
        offset_speed5 = config5.get("offset_speed", 80)
        offset_speed6 = config6.get("offset_speed", 80)
        home_speed5 = config5.get("home_speed", 80)
        home_speed6 = config6.get("home_speed", 80)
        home_dir_5 = config5.get("home_direction", "CCW")
        
        # Use the higher speed for coordinated movements
        coord_speed = max(home_speed5, home_speed6)
        offset_speed = max(offset_speed5, offset_speed6)
        
        logger.info(f"Joint 4 homing: speed={coord_speed}, offset={offset5}")
        
        # Phase 1: Move both motors in OPPOSITE directions until motor 5's endstop is hit
        logger.info("Phase 1: Moving both motors in opposite directions until motor 5 endstop...")

        # Determine direction - motor 5's homing direction
        from .mks_servo_can.mks_enums import Direction
        direction_5 = Direction.CCW if home_dir_5.upper() == "CCW" else Direction.CW
        direction_6_opposite = Direction.CW if direction_5 == Direction.CCW else Direction.CCW

        # Start both motors in opposite directions
        servo5.run_motor_in_speed_mode(direction_5, coord_speed, 150)
        servo6.run_motor_in_speed_mode(direction_6_opposite, coord_speed, 150)

        # Wait for motor 5's limit switch
        limit_hit = False
        max_wait_time = 30.0
        start_time = time.time()

        while not limit_hit and (time.time() - start_time) < max_wait_time:
            try:
                io_status = servo5.read_io_port_status()  # Check motor 5's endstop
                if io_status is not None:
                    limit1_triggered = bool(io_status & 0x01)
                    # Assuming Low level endstop
                    limit_hit = not limit1_triggered

                    if limit_hit:
                        logger.info(f"Motor 5 endstop triggered (IO: 0x{io_status:02X})")
                        break

                time.sleep(0.05)

            except Exception as e:
                logger.warning(f"Error reading motor 5 IO status: {e}")
                time.sleep(0.05)

        # Stop both motors
        servo5.stop_motor_in_speed_mode(255)
        servo6.stop_motor_in_speed_mode(255)
        time.sleep(0.2)

        if not limit_hit:
            logger.warning("Timeout waiting for motor 5 endstop")

        # Phase 2: Move both motors by motor 5's offset amount
        if offset5 != 0:
            logger.info(f"Phase 2: Moving both motors by motor 5 offset ({offset5}) at speed {offset_speed}...")
            servo5.run_motor_relative_motion_by_axis(offset_speed, 150, offset5)
            servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1*offset5)
            # Wait for both to complete
            time.sleep(0.1)
            while servo5.is_motor_running() or servo6.is_motor_running():
                time.sleep(0.05)
        servo5.set_current_axis_to_zero()
        servo6.set_current_axis_to_zero()
        logger.info("Joint 4 homing completed successfully")
        
    def _home_joint_5_same_direction(self) -> None:
        """Homing sequence for joint 5 (motor 6) - Same direction strategy.
        
        This homes joint 5 by moving motors 5 and 6 in the same direction until motor 6's endstop is hit.
        """
        logger.info("Homing joint 5 using same-direction method")
        
        # Get servo instances
        servo5 = self.servos[4]  # Motor 5 (joint index 4)
        servo6 = self.servos[5]  # Motor 6 (joint index 5)
        
        # Get motor configurations
        config5 = self.get_motor_config(4)  # Motor 5
        config6 = self.get_motor_config(5)  # Motor 6
        
        # Get homing parameters
        offset6 = config6.get("homing_offset", 20000)
        
        # Get homing speeds and directions from motor configs
        offset_speed5 = config5.get("offset_speed", 80)
        offset_speed6 = config6.get("offset_speed", 80)
        home_speed5 = config5.get("home_speed", 80)
        home_speed6 = config6.get("home_speed", 80)
        home_dir_6 = config6.get("home_direction", "CCW")
        
        # Use the higher speed for coordinated movements
        coord_speed = max(home_speed5, home_speed6)
        offset_speed = max(offset_speed5, offset_speed6)
        
        logger.info(f"Joint 5 homing: speed={coord_speed}, offset={offset6}")
        
        # Move both motors in SAME direction until motor 6's endstop is hit
        logger.info("Moving both motors in same direction until motor 6 endstop...")
        max_wait_time = 30.0
        start_time = time.time()
        
        # Motor 6 in its homing direction, motor 5 in same direction
        from .mks_servo_can.mks_enums import Direction
        dir_6 = Direction.CCW if home_dir_6.upper() == "CCW" else Direction.CW

        servo5.run_motor_in_speed_mode(dir_6, coord_speed, 150)
        servo6.run_motor_in_speed_mode(dir_6, coord_speed, 150)

        # Wait for motor 6's limit switch
        limit_hit = False
        while not limit_hit and (time.time() - start_time) < max_wait_time:
            try:
                io_status = servo6.read_io_port_status()  # Check motor 6's endstop
                if io_status is not None:
                    limit1_triggered = bool(io_status & 0x01)
                    # Assuming Low level endstop
                    limit_hit = not limit1_triggered

                    if limit_hit:
                        logger.info(f"Motor 6 endstop triggered (IO: 0x{io_status:02X})")
                        break

                time.sleep(0.05)

            except Exception as e:
                logger.warning(f"Error reading motor 6 IO status: {e}")
                time.sleep(0.05)
                
        servo5.stop_motor_in_speed_mode(255)
        servo6.stop_motor_in_speed_mode(255)
        time.sleep(0.2)

        if not limit_hit:
            logger.warning("Timeout waiting for motor 6 endstop")

        # Apply offset if configured
        if offset6 != 0:
            logger.info(f"Phase 2: Moving both motors by motor 6 offset ({offset6}) at speed {offset_speed}...")
            servo5.run_motor_relative_motion_by_axis(offset_speed, 150, -1* offset6)
            servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1 *offset6)
            time.sleep(0.2)
            # Wait for both to start moving
            start_timeout = 2.0  # seconds
            start_time = time.time()
            while not (servo5.is_motor_running() and servo6.is_motor_running()) and (time.time() - start_time) < start_timeout:
                time.sleep(0.01)

            # Wait for both to complete
            while servo5.is_motor_running() or servo6.is_motor_running():
                time.sleep(0.05)
                
        servo5.set_current_axis_to_zero()
        servo6.set_current_axis_to_zero()
        logger.info("Joint 5 homing completed successfully")


                
    def _home_motors_5_and_6(self) -> None:
        """Full coordinated homing process for motors 5 and 6 (end effector with bevel gears).
        
        This performs a complete homing sequence for both joints 4 and 5:
        1. First homes joint 4 using opposite-directions method
        2. Then homes joint 5 using same-direction method
        
        The joints are homed sequentially (not simultaneously) to avoid mechanical interference.
        """
        logger.info("Starting full coordinated homing for joints 4 and 5")
        
        # First home joint 4 (motor 5) using opposite-directions method
        self._home_joint_4_opposite_directions()
        
        # Then home joint 5 (motor 6) using same-direction method
        self._home_joint_5_same_direction()
        
        logger.info("Full coordinated homing of joints 4 and 5 completed successfully")


    def send_joint_targets(self, q: List[float], t_s: Optional[float] = None):
        """
        Send joint targets directly to motors (no coupling logic here).
        Joint-to-motor transformation should be handled at a higher level.
        
        Args:
            q: List of motor angles in radians [motor0, motor1, motor2, motor3, motor4, motor5]
            t_s: Optional duration hint (unused for CAN execution)
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
            logger.error(f"Expected 6 motor angles, got {len(q)}")
            return

        angles_rad = list(q)
        
        # Transform joint angles to motor angles (handles coupled mode)
        motor_commands = self.joints_to_motors(angles_rad)
        
        def _move_servo(motor_id: int, angle_rad: float):
            try:
                encoder_val = self.angle_to_encoder(angle_rad, motor_id)
                logger.debug(f"Motor {motor_id}: {math.degrees(angle_rad):.2f}° -> enc {encoder_val}")
                
                with self._servo_lock:
                    if motor_id >= len(self.servos):
                        logger.error(f"Servo index {motor_id} out of range")
                        return False
                    
                    # Get current position to determine movement direction
                    current_encoder = self._read_encoder_with_fallback(motor_id, self.servos[motor_id])
                    if current_encoder is None:
                        logger.warning(f"Could not read current position for motor {motor_id}, skipping movement check")
                    else:
                        # Determine direction
                        if encoder_val > current_encoder:
                            direction = 'CW'
                        elif encoder_val < current_encoder:
                            direction = 'CCW'
                        else:
                            direction = None  # No movement
                        
                        # Check if movement is allowed
                        if direction and not self.is_movement_allowed(motor_id, direction):
                            logger.warning(f"Absolute movement not allowed for motor {motor_id} in direction {direction} due to coupled endstop constraint")
                            return False
                    
                    # Get motor-specific speed and acceleration
                    motor_config = self.get_motor_config(motor_id)
                    speed = motor_config['speed_rpm']
                    acc = motor_config['acceleration']
                    
                    result = self.servos[motor_id].run_motor_absolute_motion_by_axis(
                        speed, acc, encoder_val
                    )
                    
                    if result is None:
                        logger.warning(f"Failed to send command to servo {motor_id+1}")
                        return False
                    
                    return True
                    
            except Exception as e:
                logger.error(f"Failed to send command to servo {motor_id+1}: {e}")
                return False

        # Cancel previous pending futures
        self._cancel_pending_futures()

        # Submit new futures with error handling
        futures = []
        with self._futures_lock:
            try:
                for motor_id, angle in motor_commands.items():
                    if motor_id >= len(self.servos):
                        logger.warning(f"Skipping motor {motor_id}, no corresponding servo")
                        continue
                    
                    future = self.thread_pool.submit(_move_servo, motor_id, angle)
                    futures.append(future)
                
                self.pending_futures = futures
                logger.info(f"Joint targets submitted to {len(futures)} motors")
                
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

        Args:
            arbitration_id (int): The CAN ID for the message (e.g., 0x07).
            data (List[int]): A list of integers representing the data payload (0-255).
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized. Cannot send gripper command.")
            return

        try:
            # Ensure data is a bytearray (some backends require this)
            msg_data = bytearray(data)

            # Construct the CAN message
            msg = can.Message(
                arbitration_id=arbitration_id,
                data=msg_data,
                is_extended_id=False  # Standard 11-bit ID
            )

            # Send the message
            self.bus.send(msg)
            time.sleep(0.01)  # Small delay to ensure message is sent
            # Log the sent message
            data_bytes = ', '.join([f'0x{byte:02X}' for byte in msg.data])
            logger.debug(f"Sent CAN message: ID=0x{msg.arbitration_id:X}, Data=[{data_bytes}]")

        except can.CanError as e:
            logger.error(f"Error sending CAN message: {e}")



    def open_gripper(self) -> None: 
        """
        Opens the gripper with default force.

        Raises:
            Exception: If there is an issue sending the open gripper command.

        """
        try:
            self.send_can_message_gripper(0x07, [0xFF])
            logger.info("Gripper opened with default force.")
        except Exception as e:
            logger.error(f"Error sending open gripper command: {e}")
        

    def close_gripper(self) -> None: 
        """
        Closes the gripper with default force.

        Raises:
            Exception: If there is an issue sending the close gripper command.

        """
        try:
            self.send_can_message_gripper(0x07, [0x00])
            logger.info("Gripper closed with default force.")

        except Exception as e:
            logger.error(f"Error sending close gripper command: {e}")

    def set_gripper_position(self, position: float) -> None: 
        """
        Set gripper to specific opening width with default force.

        Args:
            position (float): Position (0.0 = closed, 1.0 = open)
        """
        try:
            # Clamp position to valid range
            clamped_position = max(0.0, min(1.0, position))
            # Map 0.0-1.0 to 0x00-0xFF
            data_value = int(clamped_position * 255)
            self.send_can_message_gripper(0x07, [data_value])
            logger.info(f"Gripper set to position {clamped_position} with default force.")
        except Exception as e:
            logger.error(f"Error sending set gripper position command: {e}")



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
            motor_angles = []
            motor_encoders = []
            for i, servo in enumerate(self.servos):
                encoder_value = self._read_encoder_with_fallback(i, servo)
                motor_encoders.append(encoder_value)
                angle_rad = self.encoder_to_angle(encoder_value, i)
                motor_angles.append(angle_rad)
            
            # Apply direction inversion for joints 1, 2, 4, 5 (motors 1, 2, 4, 5)
            for i in range(len(motor_angles)):
                if i in [1, 2, 4, 5]:
                    motor_angles[i] = -motor_angles[i]
            
            # Convert motor angles to joint angles for coupled mode
            coupled_mode = self.config_manager.get('joints.coupled_mode', False)
            if coupled_mode and len(motor_angles) >= 6:
                # For coupled joints 4 and 5
                motor4_angle = motor_angles[4]
                motor5_angle = motor_angles[5]
                
                # Inverse kinematics for coupled joints
                joint4 = (motor4_angle - motor5_angle) / 2
                joint5 = (motor4_angle + motor5_angle) / 2
                
                q = motor_angles[:4] + [joint4, joint5]
            else:
                q = motor_angles
            
            # Read joint velocities with error handling
            for i, servo in enumerate(self.servos):
                try:
                    speed = servo.read_motor_speed()
                    if speed is not None and i in [1, 2, 4, 5]:
                        speed = -speed
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

        # Update current limits for movement validation
        self.current_limits = limits
        
        # Check and enforce coupled limit constraints
        self.check_and_enforce_coupled_limits()

        return {"q": q, "dq": dq, "error": error, "limits": limits, "motor_encoders": motor_encoders}

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
        
        self.velocity_active = [False] * 6
        self.velocity_direction = [None] * 6

    def start_joint_velocity(self, joint_index: int, scale: float) -> None:
        """
        Start velocity control for a joint, handling coupled mode.
        
        Args:
            joint_index: Joint index (0-5)
            scale: Speed scale from -1.0 to 1.0 (negative = reverse)
        """
        if joint_index < 0 or joint_index >= len(self.velocity_active):
            logger.error(f"Invalid joint index {joint_index}")
            return
        
        if self.bus is None:
            logger.warning("CAN bus not initialized.")
            return
        
        with self._servo_lock:
            # Transform joint velocity scale to motor velocity scales
            motor_scales = self.joint_velocity_to_motors(joint_index, scale)
            
            for motor_id, motor_scale in motor_scales.items():
                if motor_id >= len(self.servos):
                    logger.error(f"Servo index {motor_id} out of range")
                    continue
                
                if self.velocity_active[motor_id]:
                    # Already active, no need to send again
                    continue
                
                try:
                    # Get motor-specific config and scale speed
                    motor_config = self.get_motor_config(motor_id)
                    max_speed = motor_config['speed_rpm']
                    motor_speed = motor_scale * max_speed
                    
                    direction = Direction.CW if motor_speed >= 0 else Direction.CCW
                    abs_speed = abs(int(motor_speed))
                    
                    # Check if movement is allowed considering coupled endstops
                    direction_str = 'CW' if direction == Direction.CW else 'CCW'
                    if not self.is_movement_allowed(motor_id, direction_str):
                        logger.warning(f"Movement not allowed for motor {motor_id} in direction {direction_str} due to coupled endstop constraint")
                        continue
                    
                    # Get motor-specific acceleration
                    acc = motor_config['acceleration']
                    
                    self.servos[motor_id].run_motor_in_speed_mode(direction, abs_speed, acc)
                    self.velocity_active[motor_id] = True
                    self.velocity_direction[motor_id] = direction_str
                    logger.debug(f"Started velocity control for motor {motor_id}: speed={motor_speed} RPM (scale={motor_scale}, max={max_speed})")
                except Exception as e:
                    logger.error(f"Failed to start velocity control for motor {motor_id}: {e}")

    def stop_joint_velocity(self, joint_index: int, acceleration: Optional[int] = 255) -> None:
        """
        Stop velocity control for a joint, handling coupled mode.

        Args:
            joint_index: Joint index (0-5)
            acceleration (Optional[int]): Acceleration to use for stopping (default: 255)
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized.")
            return

        with self._servo_lock:
            # Get motors affected by this joint
            motor_speeds = self.joint_velocity_to_motors(joint_index, 0)  # Speed doesn't matter for stopping

            for motor_id in motor_speeds.keys():
                if motor_id < 0 or motor_id >= len(self.servos):
                    continue

                try:
                    self.servos[motor_id].stop_motor_in_speed_mode(acceleration)
                    self.velocity_active[motor_id] = False
                    self.velocity_direction[motor_id] = None
                    logger.debug(f"Stopped velocity control for motor {motor_id} with acceleration {acceleration}")
                except Exception as e:
                    logger.error(f"Failed to stop velocity control for motor {motor_id}: {e}")

    def handle_limits(self, feedback: Dict[str, Any]) -> bool:
        """
        Handle limit switches based on feedback.
        Logs limit hits but does not pause execution.
        """
        limits = feedback.get("limits", [])
        dq = feedback.get("dq", [])
        
        if len(limits) != len(dq):
            logger.warning("Mismatch between limits and velocity feedback lengths")
            return False
        
        # Check if any servo is at limit and stopped
        for i, (lim, vel) in enumerate(zip(limits, dq)):
            # Check if any limit is hit (assuming False means limit hit)
            if len(lim) >= 2 and any(lim):
                logger.warning(f"Limit hit on axis {i}: {lim}, velocity: {vel}")
        
        # Always return False to prevent blocking movements
        return False

    def reload_config(self) -> None:
        """Reload configuration from file."""
        try:
            # Reload the config manager's config from disk
            self.config_manager.config = self.config_manager.load_config()
            
            # Reload motor configurations
            motor_configs = self.config_manager.get('can_driver.motors', [])
            self.motor_configs = {}
            for mc in motor_configs:
                self.motor_configs[mc['id']] = {
                    'speed_rpm': mc.get('speed_rpm', self.default_speed),
                    'acceleration': mc.get('acceleration', self.default_acc),
                    'homing_offset': mc.get('homing_offset', 0),
                    'home_direction': mc.get('home_direction', 'CCW'),
                    'home_speed': mc.get('home_speed', 50),
                    'offset_speed': mc.get('offset_speed', 100),
                    'endstop_level': mc.get('endstop_level', 'Low')
                }
            
            # Reload other settings
            self.gear_ratios = self.config_manager.get('can_driver.gear_ratios', [1.0] * 6)
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            raise
    def __del__(self):
        """Cleanup on destruction."""
        try:
            self._cancel_pending_futures()
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=False)
        except Exception:
            pass  # Ignore cleanup errors