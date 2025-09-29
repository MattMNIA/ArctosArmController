#!/usr/bin/env python3
"""
Break In Motors Script - Specifically for Joint 4 (Motor 5)

This script initializes the motion service with a CAN driver and then
makes joint 4 move at maximum speed forwards for 10 seconds,
then backwards for 10 seconds on repeat.

Features:
- Monitors motor shaft angle errors for motors 4 and 5
- If error exceeds 10,000, plays a notification sound and stops motors
- Waits for user input to resume operation
- Press Ctrl+C to stop the script completely

Usage:
    python backend/scripts/BreakInMotors.py

Press Ctrl+C to stop the script.
"""

import sys
import os
import time
import signal
import logging
import platform

# Add the parent directory to the sys.path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.drivers import CanDriver, CompositeDriver
from core.motion_service import MotionService
import utils.logger  # Import to trigger logging setup

# Import winsound for notification sound (Windows only)
import winsound

# Configure logging
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

def check_motor_errors(driver, error_threshold=10000):
    """Check if any motor has an error exceeding the threshold.
    
    Returns:
        tuple: (has_error, max_error, motor_with_max_error)
    """
    try:
        feedback = driver.get_feedback()
        errors = feedback.get("error", [])
        
        if not errors:
            return False, 0, -1
        
        # Check motors 4 and 5 (indices 4 and 5) since joint 4 uses both
        motor_errors = []
        for i in [4, 5]:  # Motors 4 and 5 (0-indexed)
            if i < len(errors):
                motor_errors.append((i, errors[i]))
        
        if not motor_errors:
            return False, 0, -1
        
        # Find the motor with the highest error
        max_error_motor, max_error = max(motor_errors, key=lambda x: abs(x[1]))
        
        if abs(max_error) > error_threshold:
            return True, max_error, max_error_motor
        
        return False, 0, -1
        
    except Exception as e:
        logger.warning(f"Error checking motor errors: {e}")
        return False, 0, -1

def play_error_sound():
    """Play a notification sound when an error is detected."""
    if platform.system() == "Windows":
        try:
            # Play a system beep sound
            winsound.Beep(800, 1000)  # 800 Hz for 1 second
        except Exception as e:
            logger.warning(f"Could not play error sound: {e}")
    else:
        # For non-Windows systems, you could use other methods
        print("\a")  # ASCII bell character

def wait_for_motor_stop(driver, joint_index, timeout=5.0):
    """Wait for a joint to actually stop moving.
    
    Args:
        driver: The driver instance
        joint_index: The joint index to check
        timeout: Maximum time to wait in seconds
        
    Returns:
        bool: True if motor stopped successfully, False if timeout
    """
    logger.debug(f"Waiting for joint {joint_index} to stop...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            feedback = driver.get_feedback()
            velocities = feedback.get("dq", [])
            
            if joint_index < len(velocities):
                velocity = abs(velocities[joint_index])
                if velocity < 0.1:  # Consider stopped if velocity is very low
                    logger.debug(f"Joint {joint_index} has stopped (velocity: {velocity})")
                    return True
            
            time.sleep(0.05)  # Check every 50ms
            
        except Exception as e:
            logger.warning(f"Error checking motor velocity: {e}")
            time.sleep(0.1)
    
    logger.warning(f"Timeout waiting for joint {joint_index} to stop")
    return False

def wait_for_user_input():
    """Wait for user input to resume operation."""
    try:
        print("\n" + "="*50)
        print("ERROR DETECTED! Motors have been stopped.")
        print("Please fix the issue and press Enter to resume...")
        print("="*50)
        input()  # Wait for user to press Enter
        print("Resuming operation...")
        return True
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return False

def main():
    # Initialize CAN Driver
    logger.info("Initializing CAN Driver...")
    driver = CanDriver()
    
    # Initialize Motion Service
    logger.info("Starting Motion Service...")
    motion_service = MotionService(driver=driver, loop_hz=50)
    
    # Set up websocket emit function as a no-op (helps with notifications)
    motion_service.ws_emit = lambda event, data: None
    motion_service.has_active_connections = lambda: False
    
    # Start the motion service (this will handle connect and enable)
    motion_service.start()
    
    # Allow time for initialization
    time.sleep(2)
    
    # Define break-in parameters
    target_joint = 4  # Joint 4 (Motor 5)
    max_velocity = 0.75  # Maximum velocity (scale from 0.0 to 1.0)
    cycle_duration = 60  # Seconds per direction
    error_threshold = 10000  # Error threshold for motor shaft angle error
    
    # Register Ctrl+C handler
    def signal_handler(sig, frame):
        logger.info("Stopping break-in process...")
        driver.start_joint_velocity(target_joint, 0.0)
        motion_service.stop()
        logger.info("Break-in process stopped.")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        logger.info(f"Starting break-in cycle for joint {target_joint}...")
        logger.info("Press Ctrl+C to stop.")
        logger.info(f"Error monitoring active - will alert if motor error exceeds {error_threshold}")
        
        # Test the notification sound
        logger.info("Testing notification sound...")
        play_error_sound()
        logger.info("Notification sound test complete. Starting break-in cycles.")
        
        cycle_count = 0
        while True:
            cycle_count += 1
            
            # Move forward
            logger.info(f"Cycle {cycle_count}: Moving joint {target_joint} forward at max speed for {cycle_duration} seconds")
            driver.start_joint_velocity(target_joint, max_velocity)
            
            # Monitor for errors during forward movement
            start_time = time.time()
            while time.time() - start_time < cycle_duration:
                has_error, max_error, motor_id = check_motor_errors(driver, error_threshold)
                if has_error:
                    logger.error(f"ERROR DETECTED! Motor {motor_id} error: {max_error} (threshold: {error_threshold})")
                    driver.stop_joint_velocity(target_joint, 100)
                    wait_for_motor_stop(driver, target_joint)  # Wait for motor to actually stop
                    play_error_sound()
                    
                    if not wait_for_user_input():
                        raise KeyboardInterrupt("User cancelled operation")
                    
                    # Restart the cycle after user input
                    break
                
                time.sleep(0.1)  # Check every 100ms
            else:
                # Normal completion - stop and wait for motor to actually stop
                driver.stop_joint_velocity(target_joint, 100)
                wait_for_motor_stop(driver, target_joint)  # Wait for motor to actually stop
                time.sleep(0.5)  # Brief pause
                # Continue to backward movement
            
            # Move backward
            logger.info(f"Cycle {cycle_count}: Moving joint {target_joint} backward at max speed for {cycle_duration} seconds")
            driver.start_joint_velocity(target_joint, -max_velocity)
            
            # Monitor for errors during backward movement
            start_time = time.time()
            while time.time() - start_time < cycle_duration:
                has_error, max_error, motor_id = check_motor_errors(driver, error_threshold)
                if has_error:
                    logger.error(f"ERROR DETECTED! Motor {motor_id} error: {max_error} (threshold: {error_threshold})")
                    driver.stop_joint_velocity(target_joint, 100)
                    wait_for_motor_stop(driver, target_joint)  # Wait for motor to actually stop
                    play_error_sound()
                    
                    if not wait_for_user_input():
                        raise KeyboardInterrupt("User cancelled operation")
                    
                    # Restart the cycle after user input
                    break
                
                time.sleep(0.1)  # Check every 100ms
            else:
                # Normal completion - stop and wait for motor to actually stop
                driver.stop_joint_velocity(target_joint, 100)
                wait_for_motor_stop(driver, target_joint)  # Wait for motor to actually stop
                time.sleep(0.5)  # Brief pause
                logger.info(f"Completed cycle {cycle_count}")
                continue
            
            # If we get here, an error occurred and we need to restart the cycle
            logger.info("Restarting cycle after error resolution...")
            
    except Exception as e:
        logger.error(f"Error during break-in process: {e}")
        
    finally:
        # Ensure we stop the motor and shut down properly
        logger.info("Stopping motion...")
        driver.stop_joint_velocity(target_joint, 100)
        # Wait for the motor to stop and verify it stopped
        wait_for_motor_stop(driver, target_joint)
        
        logger.info("Shutting down Motion Service...")
        motion_service.stop()
        
        logger.info("Break-in process completed.")

if __name__ == "__main__":
    main()
