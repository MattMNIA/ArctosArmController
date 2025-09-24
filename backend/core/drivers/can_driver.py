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
        self.coupled_mode = self.config_manager.get('can_driver.coupled_axis_mode', False)
        logger.info(f"CanDriver initialized with coupled_mode={self.coupled_mode}")
        self.gear_ratios = self.config_manager.get('can_driver.gear_ratios', [1.0] * 6)
        self.encoder_resolution = self.config_manager.get('can_driver.encoder_resolution', 16384)
        self.can_interface = self.config_manager.get('can_driver.can_interface', 'COM4')
        self.bitrate = self.config_manager.get('can_driver.bitrate', 500000)
        self.default_speed = self.config_manager.get('can_driver.default_speed', 200)
        self.default_acc = self.config_manager.get('can_driver.default_acc', 50)
        
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
        
        # Add locks for thread safety
        self._servo_lock = threading.RLock()  # Reentrant lock for servo operations
        self._futures_lock = threading.Lock()  # For managing futures list
        self.velocity_active = [False] * 6  # Track which joints have active velocity control

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
        """Home specific joints using the configured homing parameters."""
        if self.bus is None:
            logger.warning("CAN bus not initialized. Call connect() first.")
            return
        
        with self._servo_lock:
            if not self.servos:
                logger.warning("Servos not enabled. Call enable() first.")
                return

        # Load servo settings
        config_manager = ConfigManager(Path("backend/config/mks_settings.yaml"))
        
        # Cancel any pending futures before starting homing
        self._cancel_pending_futures()
        
        # Submit homing tasks for all joints concurrently
        futures = []
        with self._futures_lock:
            try:
                for joint_idx in joint_indices:
                    if joint_idx < 0 or joint_idx >= len(self.servos):
                        logger.error(f"Invalid joint index {joint_idx}, must be between 0 and {len(self.servos)-1}")
                        continue
                    
                    future = self.thread_pool.submit(self._home_single_joint, joint_idx, config_manager)
                    futures.append(future)
                
                self.pending_futures = futures
                logger.info(f"Homing tasks submitted for {len(futures)} joints")
                
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

    def _home_single_joint(self, joint_idx: int, config_manager: ConfigManager) -> None:
        """Home a single joint (runs in separate thread)."""
        servo = self.servos[joint_idx]
        servo_config = config_manager.get(f"servo_{joint_idx}", {})
        
        try:
            # Check if this is one of the motors that needs custom homing (motors 4, 5, 6 = indices 3, 4, 5)
            if joint_idx in [3, 4, 5]:  # Motors 4, 5, 6
                self._custom_home_joint(joint_idx, servo, servo_config)
            else:
                # Use standard homing for other motors
                servo.b_go_home()
                while servo.is_motor_running():
                    time.sleep(0.05)
                
                # Apply homing offset if configured
                homing_offset = servo_config.get("homing_offset", 0)
                home_speed = servo_config.get("home_speed", 50)
                if homing_offset != 0:
                    servo.run_motor_relative_motion_by_axis(int(home_speed), 150, -1*int(homing_offset))
                    while servo.is_motor_running():
                        time.sleep(0.05)
                
                servo.set_current_axis_to_zero()
                logger.info(f"Successfully homed joint {joint_idx} using standard method")
            
        except Exception as e:
            logger.error(f"Failed to home joint {joint_idx}: {e}")
            raise

    def _custom_home_joint(self, joint_idx: int, servo, servo_config: dict) -> None:
        """Custom homing process for motors 4, 5, 6 with different procedures for each."""
        logger.info(f"Starting custom homing for joint {joint_idx} (motor {joint_idx + 1})")
        
        if joint_idx == 3:  # Motor 4
            self._home_motor_4(servo, servo_config)
        elif joint_idx in [4, 5]:  # Motors 5 and 6 - home together
            # Only home if this is motor 5 (index 4), motor 6 will be handled by motor 5's homing
            if joint_idx == 4:
                self._home_motors_5_and_6()
        else:
            raise ValueError(f"Custom homing not implemented for joint {joint_idx}")

    def _home_motor_4(self, servo, servo_config: dict) -> None:
        """Custom homing process for motor 4 (joint index 3)."""
        logger.info("Motor 4: Starting custom homing procedure")
        
        # Get homing parameters from config
        home_direction_str = servo_config.get("home_direction", "CW")
        home_speed = servo_config.get("home_speed", 90)
        homing_offset = servo_config.get("homing_offset", 117160)
        endstop_level_str = servo_config.get("endstop_level", "Low")
        
        # Convert string values to enums
        from .mks_servo_can.mks_enums import Direction, EndStopLevel
        home_direction = Direction.CCW if home_direction_str.upper() == "CCW" else Direction.CW
        endstop_level = EndStopLevel.Low if endstop_level_str.upper() == "LOW" else EndStopLevel.High
        
        logger.info(f"Motor 4: direction={home_direction.name}, speed={home_speed}, offset={homing_offset}, endstop_level={endstop_level.name}")
        
        # Motor 4 specific homing logic
        # Step 1: Move motor in homing direction until limit switch is triggered
        logger.info("Motor 4: Moving until limit hit...")
        
        # Start moving at homing speed
        servo.run_motor_in_speed_mode(home_direction, int(home_speed), 150)
        
        # Wait for limit switch to be triggered
        limit_hit = False
        max_wait_time = 30.0
        start_time = time.time()
        
        while not limit_hit and (time.time() - start_time) < max_wait_time:
            try:
                io_status = servo.read_io_port_status()
                if io_status is not None:
                    limit2_triggered = bool(io_status & 0x02)
                    if endstop_level == EndStopLevel.Low:
                        limit_hit = not limit2_triggered
                    else:
                        limit_hit = limit2_triggered
                    
                    if limit_hit:
                        logger.info(f"Motor 4: Limit 2 switch triggered (IO: 0x{io_status:02X})")
                        break
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.warning(f"Motor 4: Error reading IO status: {e}")
                time.sleep(0.05)
        
        # Stop the motor
        servo.stop_motor_in_speed_mode(255)
        time.sleep(0.1)
        
        if not limit_hit:
            logger.warning("Motor 4: Timeout waiting for limit switch")
        
        # Step 2: Move the homing offset
        if homing_offset != 0:
            logger.info(f"Motor 4: Moving offset of {homing_offset}...")
            servo.run_motor_relative_motion_by_axis(int(home_speed), 150, -1 * int(homing_offset)) # Change direction of homing offset
            time.sleep(0.1) # Small delay to ensure command is sent
            while servo.is_motor_running():
                time.sleep(0.05)
        
        # Step 3: Set current position to zero
        servo.set_current_axis_to_zero()
        logger.info("Motor 4: Custom homing completed")

    def _home_motor_5(self, servo, servo_config: dict) -> None:
        """Custom homing process for motor 5 (joint index 4)."""
        # logger.info("Motor 5: Starting custom homing procedure")
        
        # # Get homing parameters from config
        # home_direction_str = servo_config.get("home_direction", "CCW")
        # home_speed = servo_config.get("home_speed", 80)
        # homing_offset = servo_config.get("homing_offset", 25000)
        # endstop_level_str = servo_config.get("endstop_level", "Low")
        
        # # Convert string values to enums
        # from .mks_servo_can.mks_enums import Direction, EndStopLevel
        # home_direction = Direction.CCW if home_direction_str.upper() == "CCW" else Direction.CW
        # endstop_level = EndStopLevel.Low if endstop_level_str.upper() == "LOW" else EndStopLevel.High
        
        # logger.info(f"Motor 5: direction={home_direction.name}, speed={home_speed}, offset={homing_offset}, endstop_level={endstop_level.name}")
        
        # # Motor 5 specific homing logic
        # # Step 1: Move motor in homing direction until limit switch is triggered
        # logger.info("Motor 5: Moving until limit hit...")
        
        # # Start moving at homing speed
        # servo.run_motor_in_speed_mode(home_direction, int(home_speed), 150)
        
        # # Wait for limit switch to be triggered
        # limit_hit = False
        # max_wait_time = 30.0
        # start_time = time.time()
        
        # while not limit_hit and (time.time() - start_time) < max_wait_time:
        #     try:
        #         io_status = servo.read_io_port_status()
        #         if io_status is not None:
        #             limit1_triggered = bool(io_status & 0x01)
        #             if endstop_level == EndStopLevel.Low:
        #                 limit_hit = not limit1_triggered
        #             else:
        #                 limit_hit = limit1_triggered
                    
        #             if limit_hit:
        #                 logger.info(f"Motor 5: Limit switch triggered (IO: 0x{io_status:02X})")
        #                 break
                
        #         time.sleep(0.05)
                
        #     except Exception as e:
        #         logger.warning(f"Motor 5: Error reading IO status: {e}")
        #         time.sleep(0.05)
        
        # # Stop the motor
        # servo.stop_motor_in_speed_mode(255)
        # time.sleep(0.1)
        
        # if not limit_hit:
        #     logger.warning("Motor 5: Timeout waiting for limit switch")
        
        # # Step 2: Move the homing offset
        # if homing_offset != 0:
        #     logger.info(f"Motor 5: Moving offset of {homing_offset}...")
        #     offset_direction = Direction.CW if home_direction == Direction.CCW else Direction.CCW
        #     servo.run_motor_relative_motion_by_axis(int(home_speed), 150, int(homing_offset))
        #     while servo.is_motor_running():
        #         time.sleep(0.05)
        
        # # Step 3: Set current position to zero
        # servo.set_current_axis_to_zero()
        # logger.info("Motor 5: Custom homing completed")

    def _home_motors_5_and_6(self) -> None:
        """Coordinated homing process for motors 5 and 6 (end effector with bevel gears)."""
        logger.info("Starting coordinated homing for motors 5 and 6 (end effector)")
        
        # Get servo instances
        servo5 = self.servos[4]  # Motor 5 (joint index 4)
        servo6 = self.servos[5]  # Motor 6 (joint index 5)
        
        # Load configurations
        config_manager = ConfigManager(Path("backend/config/mks_settings.yaml"))
        config5 = config_manager.get("servo_4", {})  # servo_4 is motor 5
        config6 = config_manager.get("servo_5", {})  # servo_5 is motor 6
        
        # Get homing parameters
        speed5 = config5.get("home_speed", 80)
        speed6 = config6.get("home_speed", 60)
        offset5 = config5.get("homing_offset", 25000)
        offset6 = config6.get("homing_offset", 20000)
        
        # Use the higher speed for coordinated movements
        coord_speed = max(speed5, speed6)
        
        logger.info(f"Motors 5&6: speed={coord_speed}, offset5={offset5}, offset6={offset6}")
        
        # Phase 1: Move both motors in SAME direction until motor 5's endstop is hit
        logger.info("Phase 1: Moving both motors same direction until motor 5 endstop...")
        
        # Determine direction - motor 5's homing direction
        home_dir_5 = config5.get("home_direction", "CCW")
        from .mks_servo_can.mks_enums import Direction
        direction = Direction.CCW if home_dir_5.upper() == "CCW" else Direction.CW
        
        # Start both motors in same direction
        servo5.run_motor_in_speed_mode(direction, coord_speed, 150)
        servo6.run_motor_in_speed_mode(direction, coord_speed, 150)
        
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
            logger.info(f"Phase 2: Moving both motors by motor 5 offset ({offset5})...")
            offset_direction = Direction.CW if direction == Direction.CCW else Direction.CCW
            servo5.run_motor_relative_motion_by_axis(coord_speed, 150, offset5)
            servo6.run_motor_relative_motion_by_axis(coord_speed, 150, offset5)
            
            # Wait for both to complete
            while servo5.is_motor_running() or servo6.is_motor_running():
                time.sleep(0.05)
        
        # Phase 3: Move both motors in OPPOSITE directions until motor 6's endstop is hit
        logger.info("Phase 3: Moving motors opposite directions until motor 6 endstop...")
        
        # Motor 6 in its homing direction, motor 5 in opposite
        home_dir_6 = config6.get("home_direction", "CCW")
        dir_6 = Direction.CCW if home_dir_6.upper() == "CCW" else Direction.CW
        dir_5_opposite = Direction.CW if dir_6 == Direction.CCW else Direction.CCW
        
        servo5.run_motor_in_speed_mode(dir_5_opposite, coord_speed, 150)
        servo6.run_motor_in_speed_mode(dir_6, coord_speed, 150)
        
        # Wait for motor 6's limit switch
        limit_hit = False
        start_time = time.time()
        
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
        
        # Stop both motors
        servo5.stop_motor_in_speed_mode(255)
        servo6.stop_motor_in_speed_mode(255)
        time.sleep(0.2)
        
        if not limit_hit:
            logger.warning("Timeout waiting for motor 6 endstop")
        
        # Phase 4: Move both motors in opposite directions by motor 6's offset amount
        if offset6 != 0:
            logger.info(f"Phase 4: Moving motors opposite by motor 6 offset ({offset6})...")
            # Continue in the same opposite directions
            servo5.run_motor_relative_motion_by_axis(coord_speed, 150, offset6)
            servo6.run_motor_relative_motion_by_axis(coord_speed, 150, -offset6)  # Opposite direction
            
            # Wait for both to complete
            while servo5.is_motor_running() or servo6.is_motor_running():
                time.sleep(0.05)
        
        # Phase 5: Set both motors to zero position
        servo5.set_current_axis_to_zero()
        servo6.set_current_axis_to_zero()
        
        logger.info("Motors 5 and 6 coordinated homing completed")

    def _home_motor_6(self, servo, servo_config: dict) -> None:
        """Custom homing process for motor 6 (joint index 5)."""
        # logger.info("Motor 6: Starting custom homing procedure")
        
        # # Get homing parameters from config
        # home_direction_str = servo_config.get("home_direction", "CCW")
        # home_speed = servo_config.get("home_speed", 60)
        # homing_offset = servo_config.get("homing_offset", 20000)
        # endstop_level_str = servo_config.get("endstop_level", "Low")
        
        # # Convert string values to enums
        # from .mks_servo_can.mks_enums import Direction, EndStopLevel
        # home_direction = Direction.CCW if home_direction_str.upper() == "CCW" else Direction.CW
        # endstop_level = EndStopLevel.Low if endstop_level_str.upper() == "LOW" else EndStopLevel.High
        
        # logger.info(f"Motor 6: direction={home_direction.name}, speed={home_speed}, offset={homing_offset}, endstop_level={endstop_level.name}")
        
        # # Motor 6 specific homing logic
        # # Step 1: Move motor in homing direction until limit switch is triggered
        # logger.info("Motor 6: Moving until limit hit...")
        
        # # Start moving at homing speed
        # servo.run_motor_in_speed_mode(home_direction, int(home_speed), 150)
        
        # # Wait for limit switch to be triggered
        # limit_hit = False
        # max_wait_time = 30.0
        # start_time = time.time()
        
        # while not limit_hit and (time.time() - start_time) < max_wait_time:
        #     try:
        #         io_status = servo.read_io_port_status()
        #         if io_status is not None:
        #             limit1_triggered = bool(io_status & 0x01)
        #             if endstop_level == EndStopLevel.Low:
        #                 limit_hit = not limit1_triggered
        #             else:
        #                 limit_hit = limit1_triggered
                    
        #             if limit_hit:
        #                 logger.info(f"Motor 6: Limit switch triggered (IO: 0x{io_status:02X})")
        #                 break
                
        #         time.sleep(0.05)
                
        #     except Exception as e:
        #         logger.warning(f"Motor 6: Error reading IO status: {e}")
        #         time.sleep(0.05)
        
        # # Stop the motor
        # servo.stop_motor_in_speed_mode(255)
        # time.sleep(0.1)
        
        # if not limit_hit:
        #     logger.warning("Motor 6: Timeout waiting for limit switch")
        
        # # Step 2: Move the homing offset
        # if homing_offset != 0:
        #     logger.info(f"Motor 6: Moving offset of {homing_offset}...")
        #     offset_direction = Direction.CW if home_direction == Direction.CCW else Direction.CCW
        #     servo.run_motor_relative_motion_by_axis(int(home_speed), 150, int(homing_offset))
        #     while servo.is_motor_running():
        #         time.sleep(0.05)
        
        # # Step 3: Set current position to zero
        # servo.set_current_axis_to_zero()
        # logger.info("Motor 6: Custom homing completed")

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
        
        self.velocity_active = [False] * 6

    def start_joint_velocity(self, joint_index: int, speed: float) -> None:
        """
        Start velocity control for a specific joint.
        
        Args:
            joint_index: Index of the joint (0-5)
            speed: Speed in RPM, positive for CW, negative for CCW
        """
        if joint_index < 0 or joint_index >= len(self.velocity_active):
            logger.error(f"Invalid joint index {joint_index}")
            return
        
        if self.bus is None:
            logger.warning("CAN bus not initialized.")
            return
        
        with self._servo_lock:
            # Handle coupled mode for joints 5 and 6 (indices 4 and 5)
            if self.coupled_mode and joint_index >= 4:
                logger.info(f"Coupled mode active for joint {joint_index}, coupled_mode={self.coupled_mode}")
                # Check if already active
                if self.velocity_active[joint_index]:
                    logger.debug(f"Joint {joint_index} velocity control already active")
                    return
                    
                # For differential drive: joints 5 and 6 are controlled by motors 5 and 6
                motor5_speed = speed
                motor6_speed = speed if joint_index == 5 else -speed
                
                # Start both motors
                for motor_idx, motor_speed in [(4, motor5_speed), (5, motor6_speed)]:
                    if motor_idx >= len(self.servos):
                        logger.error(f"Servo index {motor_idx} out of range")
                        continue
                    
                    try:
                        direction = Direction.CW if motor_speed >= 0 else Direction.CCW
                        abs_speed = abs(int(motor_speed))
                        self.servos[motor_idx].run_motor_in_speed_mode(direction, abs_speed, self.default_acc)
                        self.velocity_active[motor_idx] = True
                        logger.debug(f"Started velocity control for motor {motor_idx+1}: speed={motor_speed} RPM")
                    except Exception as e:
                        logger.error(f"Failed to start velocity control for motor {motor_idx+1}: {e}")
                
                # Mark both joints as active
                self.velocity_active[4] = True
                self.velocity_active[5] = True
                logger.debug(f"Started coupled velocity control for joint {joint_index}: speed={speed} RPM")
            else:
                logger.debug(f"Normal mode for joint {joint_index}, coupled_mode={self.coupled_mode}")
                # Normal single motor control
                if joint_index >= len(self.servos):
                    logger.error(f"Servo index {joint_index} out of range")
                    return
                
                if self.velocity_active[joint_index]:
                    # Already active, no need to send again
                    return
                
                try:
                    direction = Direction.CW if speed >= 0 else Direction.CCW
                    abs_speed = abs(int(speed))
                    self.servos[joint_index].run_motor_in_speed_mode(direction, abs_speed, self.default_acc)
                    self.velocity_active[joint_index] = True
                    logger.debug(f"Started velocity control for joint {joint_index}: speed={speed} RPM")
                except Exception as e:
                    logger.error(f"Failed to start velocity control for joint {joint_index}: {e}")

    def stop_joint_velocity(self, joint_index: int) -> None:
        """
        Stop velocity control for a specific joint.
        
        Args:
            joint_index: Index of the joint (0-5)
        """
        if self.bus is None:
            logger.warning("CAN bus not initialized.")
            return
        
        with self._servo_lock:
            # Handle coupled mode for joints 5 and 6 (indices 4 and 5)
            if self.coupled_mode and joint_index >= 4:
                # Stop both motors for coupled joints
                for motor_idx in [4, 5]:
                    if motor_idx < 0 or motor_idx >= len(self.servos):
                        continue
                    
                    try:
                        # Use maximum acceleration for faster stopping
                        self.servos[motor_idx].stop_motor_in_speed_mode(255)
                        self.velocity_active[motor_idx] = False
                        logger.debug(f"Stopped velocity control for motor {motor_idx+1}")
                    except Exception as e:
                        logger.error(f"Failed to stop velocity control for motor {motor_idx+1}: {e}")
                
                # Mark both joints as inactive
                self.velocity_active[4] = False
                self.velocity_active[5] = False
                logger.debug(f"Stopped coupled velocity control for joint {joint_index}")
            else:
                # Normal single motor control
                if joint_index < 0 or joint_index >= len(self.servos):
                    logger.error(f"Invalid joint index {joint_index}")
                    return
                
                try:
                    # Use maximum acceleration for faster stopping
                    self.servos[joint_index].stop_motor_in_speed_mode(255)
                    self.velocity_active[joint_index] = False
                    logger.debug(f"Stopped velocity control for joint {joint_index}")
                except Exception as e:
                    logger.error(f"Failed to stop velocity control for joint {joint_index}: {e}")

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

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self._cancel_pending_futures()
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=False)
        except Exception:
            pass  # Ignore cleanup errors