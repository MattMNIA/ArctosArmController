import time
import sys
import os
import math

# Add the backend directory to the path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.mks_servo_can.mks_servo import MksServo
from services.mks_servo_can.mks_enums import WorkMode, Enable, Direction, MotorStatus, CanBitrate, RunMotorResult, SuccessStatus

class MotorController:
    """
    High-level controller for an individual MKS servo motor.
    
    Provides initialization, degree-based motion, limit switch checking, and status querying.
    """
    
    def __init__(self, bus, notifier, can_id, pulses_per_degree=1600, limit_ports=(0, 1), scaling_factor=1.0, limit_active_high=True, encoder_resolution=16384, gear_ratios=None):
        """
        Initialize the motor controller.
        
        Args:
            bus: CAN bus instance.
            notifier: CAN notifier instance.
            can_id (int): CAN ID of the motor (1-6).
            pulses_per_degree (int): Motor resolution in pulses per degree (default: 1600 for common steppers).
            limit_ports (tuple): IO port indices for limit switches (default: (0, 1) for IN_1, IN_2).
            scaling_factor (float): Scaling factor for motion units (default: 1.0).
            limit_active_high (bool): Whether limit switches are active high (True) or active low (False).
            encoder_resolution (int): Encoder resolution in counts per revolution (default: 16384).
            gear_ratios (list): Gear ratios for each axis (default: [1.0] * 6).
        """
        self.servo = MksServo(bus, notifier, can_id)
        self.pulses_per_degree = pulses_per_degree
        self.limit_ports = limit_ports  # Indices for IO ports (0=IN_1, 1=IN_2, etc.)
        self.scaling_factor = scaling_factor
        self.limit_active_high = limit_active_high
        self.encoder_resolution = encoder_resolution
        self.gear_ratios = gear_ratios if gear_ratios is not None else [1.0] * 6  # Default gear ratios for 6 axes
        
    def startup(self):
        """
        Perform motor initialization sequence.
        
        Enables the motor, sets work mode to SR_vFOC, sets subdivisions to 16, CAN bitrate to 500k,
        sets default current, and calibrates encoder.
        """
        print(f"Initializing motor with CAN ID {self.servo.can_id}...")
        
        # Set CAN bitrate to 500k
        result = self.servo.set_can_bitrate(CanBitrate.Rate500K)
        if result != SuccessStatus.Success:
            raise RuntimeError("Failed to set CAN bitrate")
        
        # Enable motor
        result = self.servo.enable_motor(Enable.Enable)
        if result != SuccessStatus.Success:
            raise RuntimeError("Failed to enable motor")
        
        # Set work mode to SR_vFOC
        result = self.servo.set_work_mode(WorkMode.SrvFoc)
        if result != SuccessStatus.Success:
            raise RuntimeError("Failed to set work mode")
        
        print("Motor initialization complete")
        
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
    
    def move_degrees(self, degrees, speed=100, acceleration=50):
        """
        Move the motor by a specified number of degrees.
        
        Args:
            degrees (float): Degrees to move (positive for CW, negative for CCW).
            speed (int): Speed in RPM (default: 100).
            acceleration (int): Acceleration (default: 50).
        
        Raises:
            ValueError: If degrees would exceed limits or parameters are invalid.
        """
        if self.is_at_limit():
            raise ValueError("Cannot move: Motor is at limit switch")
        
        pulses = int(abs(degrees) * self.pulses_per_degree * self.scaling_factor)
        direction = Direction.CW if degrees >= 0 else Direction.CCW
            
        # Use relative motion by pulses
        result = self.servo.run_motor_relative_motion_by_pulses(
            direction, speed, acceleration, pulses
        )
        if result != RunMotorResult.RunStarting:
            raise RuntimeError(f"Failed to start motor motion. Status: {result}")
        
        # Wait for motion to complete
        self.servo.wait_for_motor_idle(timeout=10)  # 10 second timeout
    
    def is_at_limit(self):
        """
        Check if the motor has reached a limit switch.
        
        Returns:
            bool: True if any limit switch is active.
        """
        io_status = self.servo.read_io_port_status()
        if io_status is None:
            return False  # Assume not at limit if unable to read
        
        # Check specified ports
        for port in self.limit_ports:
            bit_value = (io_status & (1 << port)) != 0
            if self.limit_active_high:
                # Active high: bit set = limit activated
                if bit_value:
                    return True
            else:
                # Active low: bit clear = limit activated
                if not bit_value:
                    return True
        return False
    
    def get_status(self):
        """
        Get the current motor status.
        
        Returns:
            MotorStatus: Current status of the motor.
        """
        return self.servo.query_motor_status()
    
    def get_encoder_position(self):
        """
        Get the current encoder position.
        Returns:
            dict: Dictionary with 'carry' and 'addition' values, or None if error
        """
        carry_result = self.servo.read_encoder_value_carry()
        carry = carry_result.get('carry') if carry_result is not None else None
        addition = self.servo.read_encoder_value_addition()
        if carry is not None and addition is not None:
            return {'carry': carry, 'addition': addition}
        return None
    
    def get_encoder_degrees(self):
        """
        Get the current encoder position in degrees.
        
        Returns:
            float: Current position in degrees, or None if error
        """
        pos = self.get_encoder_position()
        if pos is not None:
            # Ensure carry and addition are integers
            carry = int(pos['carry'])
            addition = int(pos['addition'])
            # Convert encoder counts to degrees
            total_counts = (carry * 0x4000) + addition
            return total_counts / self.pulses_per_degree / self.scaling_factor
        return None
    
    def set_position_to_zero(self):
        """
        Set the current encoder position to zero (software zero).
        
        Returns:
            SuccessStatus: Success status of the operation
        """
        return self.servo.set_current_axis_to_zero()
    
    def stop(self):
        """
        Emergency stop the motor.
        """
        _ = self.servo.emergency_stop_motor()
