# core/drivers/base.py
from typing import Protocol, List, Dict, Any
from utils.logger import logger
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



class CanDriver():
    def __init__(self):
        # Load configuration
        config_path = Path(__file__).parent.parent.parent / "config" / "default.yml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        can_config = config.get('can_driver', {})
        self.coupled_mode = config.get('coupled_axis_mode', False)
        self.gear_ratios = can_config.get('gear_ratios', [1.0] * 6)
        self.encoder_resolution = can_config.get('encoder_resolution', 16384)
        self.can_interface = can_config.get('can_interface', 'COM3')
        self.bitrate = can_config.get('bitrate', 1000000)
        self.bus = None
        self.servos = []
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        self.pending_futures = []


    def is_can_interface_up(self) -> bool:
        """
        Checks if the specified CAN interface is active.

        This method checks the status of the CAN interface. On Windows, it checks if the COM port
        is available in the list of serial ports. On Linux, it uses the `ip link show` command to
        check if the interface is up.

        Returns:
            bool: True if the interface is active, False otherwise.
        """
      
        if platform.system() == "Windows":
            # On Windows, we assume the COM port is available if it appears in the port list
            import serial.tools.list_ports
            ports = [port.device for port in serial.tools.list_ports.comports()]
            return self.can_interface in ports
        else:
            try:
                result = subprocess.run(["ip", "link", "show", self.can_interface], capture_output=True, text=True)
                return "UP" in result.stdout
            except Exception as e:
                logger.error(f"Error checking CAN interface: {e}")
            return False
    
    def angle_to_encoder(self, angle_rad: float, axis_index: int) -> int:  
        """
        Converts a joint angle from radians to an encoder value for a given axis.

        This method calculates the corresponding encoder value for a given joint angle.
        The calculation takes into account the gear ratio and encoder resolution.

        Args:
            angle_rad (float): The joint angle in radians.
            axis_index (int): The index of the axis (joint) for which to convert the angle.

        Returns:
            int: The calculated encoder value for the given joint angle.
        """
        gear_ratio = self.gear_ratios[axis_index]
        encoder_value = int((angle_rad / (2 * math.pi)) * self.encoder_resolution * gear_ratio)
        return encoder_value

    def encoder_to_angle(self, encoder_value: int, axis_index: int) -> float:
        """
        Converts an encoder value to a joint angle in radians for a given axis.

        This method calculates the corresponding joint angle in radians for a given encoder value.
        The calculation accounts for the gear ratio and encoder resolution.
        
        :param encoder_value: Encoder reading.
        :param axis_index: Index of the axis.
        :return: Angle in radians.
        """
        gear_ratio = self.gear_ratios[axis_index]
        angle_rad = (encoder_value / (self.encoder_resolution * gear_ratio)) * (2 * math.pi)
        return angle_rad
    
    def _read_encoder_with_fallback(self, i: int, servo) -> int:
        """Reads encoder value for a single axis with fallback to 0 on failure."""
        try:
            encoder_value = servo.read_encoder_value_addition()  # type: ignore
            if encoder_value is None:
                logger.warning(f"Failed to read encoder value for Axis {i}, setting to 0.")
                return 0
            return encoder_value
        except Exception as e:
            logger.warning(f"Error reading encoder for Axis {i}: {e}")
            return 0
    
    def connect(self) -> None: 
        """
        Initializes the CAN bus interface.

        This method initializes the CAN bus interface, sets the bitrate, and ensures that the
        CAN interface is active. If the CAN interface is not active, it logs an error and raises
        a `RuntimeError`.

        Raises:
            RuntimeError: If the CAN interface is not available or if there is an error initializing the CAN bus.
        """
        if not self.is_can_interface_up():
            if platform.system() == "Windows":
                raise RuntimeError(f"CAN interface is not available on {self.can_interface}.")
            else:
                raise RuntimeError("CAN interface is not active. Please run 'setup_canable.sh' first.")

        try:
            if platform.system() == "Windows":
                self.bus = can.interface.Bus(bustype="slcan", channel=self.can_interface, bitrate=self.bitrate)
            else:
                self.bus = can.interface.Bus(bustype="socketcan", channel=self.can_interface)

            logger.info(f"CAN bus successfully initialized on {self.can_interface} with bitrate {self.bitrate}.")
        except Exception as e:
            logger.error(f"Error initializing CAN bus: {e}")
            raise RuntimeError("Error initializing CAN bus.")
    def enable(self) -> None:
        """
        Initializes the servo motors connected to the CAN bus.

        This method initializes each servo motor connected to the CAN bus. It configures
        the limit port on servos 3 through 6.

        Raises:
            Exception: If there is an error during the initialization of a servo motor.
        """
        logger.info("🔧 Initializing servos...")
        start_time = time.time()

        try:
            notifier = can.Notifier(cast(BusABC, self.bus), [])
        except Exception as e:
            logger.error(f"❌ Failed to create CAN notifier: {e}")
            raise

        for i in range(1, 7):
            try:
                logger.debug(f"🔹 Creating servo instance for ID {i}")
                servo = mks_servo.MksServo(self.bus, notifier, i)
                servo.enable_motor(Enable.Enable)
                self.servos.append(servo)
                logger.debug(f"✅ Servo {i} initialized.")
            except Exception as e:
                logger.debug(f"❌ Failed to initialize servo ID {i}: {e}")
                raise

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
        logger.info(f"✅ All servos initialized in {duration:.2f} seconds.")

    def disable(self) -> None:
        """
        Initializes the servo motors connected to the CAN bus.

        This method initializes each servo motor connected to the CAN bus. It configures
        the limit port on servos 3 through 6.

        Raises:
            Exception: If there is an error during the initialization of a servo motor.
        """
        logger.info("🔧 Initializing servos...")
        start_time = time.time()

        try:
            notifier = can.Notifier(cast(BusABC, self.bus), [])
        except Exception as e:
            logger.error(f"❌ Failed to create CAN notifier: {e}")
            raise

        for i in range(1, 7):
            try:
                logger.debug(f"🔹 Removing Servo {i}")
                servo = self.servos[i-1]
                servo.disable_motor(Enable.Enable)
                self.servos.remove(servo)
                logger.debug(f"✅ Servo {i} removed.")
            except Exception as e:
                logger.debug(f"❌ Failed to remove servo ID {i}: {e}")
                raise
            
        duration = time.time() - start_time
        logger.info(f"✅ All servos disabled in {duration:.2f} seconds.")
        
    def home(self) -> None: ...
    def send_joint_targets(self, q: List[float], t_s: float = 1.0):
        """
        Map MotionService send_joint_targets() to move_to_angles()
        """

        # --- Normalize acceleration and speed for now ---
        default_speed = 500
        default_acc = 150

        
        angles_rad = list(q)
        if self.coupled_mode and len(angles_rad) >= 6:
            b_axis = angles_rad[4] + angles_rad[5]
            c_axis = angles_rad[4] - angles_rad[5]
            angles_rad[4] = b_axis
            angles_rad[5] = c_axis

        # --- Internal move helper ---
        def _move_servo(i: int, angle_rad: float):
            encoder_val = self.angle_to_encoder(angle_rad, i)
            logger.debug(f"Axis {i}: {math.degrees(angle_rad):.2f}° -> enc {encoder_val}")
            self.servos[i].run_motor_absolute_motion_by_axis(
                default_speed, default_acc, encoder_val
            )

        # --- Cancel pending futures ---
        for f in self.pending_futures:
            if not f.done():
                f.cancel()
        self.pending_futures = []

        # --- Submit new futures ---
        futures = [
            self.thread_pool.submit(_move_servo, i, angle)
            for i, angle in enumerate(angles_rad)
        ]
        self.pending_futures = futures

    def get_feedback(self) -> Dict[str, Any]:
        q = []
        for i, servo in enumerate(self.servos):
            encoder_value = self._read_encoder_with_fallback(i, servo)
            angle_rad = self.encoder_to_angle(encoder_value, i)
            q.append(angle_rad)
        dq = [servo.read_motor_speed() for servo in self.servos]
        return {"q": q, "dq": dq, "faults": []}
    def estop(self) -> None:
        """
        Immediately stops all motors by sending the emergency stop command to each servo.

        This method should be called in case of emergency to halt all robot motion.
        Logs the result of each stop attempt.
        """
        if not hasattr(self, 'servos') or self.servos is None:
            logger.error("No servos initialized for emergency stop!")
            return
        for i, servo in enumerate(self.servos):
            try:
                result = servo.emergency_stop_motor()
                logger.debug(f"Emergency stop sent to servo {i}: {result}")
            except Exception as e:
                logger.error(f"Failed to send emergency stop to servo {i}: {e}")
    def __del__(self):
        """Clean up resources when the object is destroyed."""
        if hasattr(self, "thread_pool"):
            self.thread_pool.shutdown(wait=True)
