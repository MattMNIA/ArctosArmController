#!/usr/bin/env python3
"""
Test script to debug servo 2 enable issues.
Run with: python backend/scripts/test_servo_2_debug.py
"""

import logging
import sys
import os
from pathlib import Path

# Add the backend path to sys.path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.drivers.can_driver import CanDriver
from utils.config_manager import ConfigManager
from core.drivers.mks_servo_can.mks_enums import EnableStatus, Enable

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_servo_2():
    """Test enabling servo 2 specifically."""
    logger.info("Testing servo 2 enable...")

    driver = CanDriver()

    try:
        # Connect to CAN bus
        driver.connect()

        # Create servo 2 instance manually
        import can
        from core.drivers.mks_servo_can import mks_servo
        from typing import cast
        from can import BusABC

        notifier = can.Notifier(cast(BusABC, driver.bus), [])
        servo = mks_servo.MksServo(driver.bus, notifier, 2)  # Servo ID 2

        logger.info("Checking initial status...")
        try:
            status = servo.read_en_pins_status()
            logger.info(f"Initial enable status: {status}")
        except Exception as e:
            logger.error(f"Could not read initial status: {e}")

        logger.info("Checking IO port status...")
        try:
            io_status = servo.read_io_port_status()
            logger.info(f"IO port status: {io_status} (bit 0=IN1/endstop1, bit 1=IN2/endstop2)")
        except Exception as e:
            logger.error(f"Could not read IO status: {e}")

        logger.info("Attempting to enable servo...")
        try:
            servo.enable_motor(Enable.Enable)
            logger.info("Enable command sent")
        except Exception as e:
            logger.error(f"Failed to send enable command: {e}")

        # Check status multiple times
        for i in range(5):
            try:
                status = servo.read_en_pins_status()
                logger.info(f"Status check {i+1}: {status}")
                if status == EnableStatus.Enabled:
                    logger.info("✅ Servo enabled successfully!")
                    break
            except Exception as e:
                logger.error(f"Status check {i+1} failed: {e}")

            import time
            time.sleep(0.5)

        logger.info("Test complete")

    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        if driver.bus:
            driver.bus.shutdown()

if __name__ == "__main__":
    test_servo_2()