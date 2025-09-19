import logging
import sys
import os
from pathlib import Path

# Add the backend path to sys.path so we can import the modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core.drivers.can_driver import CanDriver
from utils.config_manager import ConfigManager
from core.drivers.mks_servo_can.mks_enums import EndStopLevel, Enable, Direction

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings_mapping = [{
    "motorId": 1,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
},{
    "motorId": 2,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
},{
    "motorId": 3,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
},{
    "motorId": 4,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
},{
    "motorId": 5,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
},{
    "motorId": 6,
    "homeTrig": EndStopLevel.High,
    "homeDir": Direction.CCW,
    "homeSpeed": 50,
    "endLimit": Enable.Enable
}]

def main():
    # Initialize CAN driver
    driver = CanDriver()
    driver.connect()
    driver.enable()

    # For each motor, set home and go home
    for i, servo in enumerate(driver.servos):
        if i != 4:
            continue
        try:
            logger.info(f"Setting home for motor {i + 1}")
            result = servo.set_home(homeTrig = settings_mapping[i]["homeTrig"], homeDir = settings_mapping[i]["homeDir"], homeSpeed = settings_mapping[i]["homeSpeed"], endLimit = settings_mapping[i]["endLimit"])
            logger.info(f"Set home result for motor {i + 1}: {result}")

            logger.info(f"Going home for motor {i + 1}")
            result = servo.nb_go_home()
            logger.info(f"Go home result for motor {i + 1}: {result}")

            # Wait for homing to complete
            servo.wait_for_go_home()
            logger.info(f"Homing completed for motor {i + 1}")

        except Exception as e:
            logger.error(f"Failed to set home and go home for motor {i + 1}: {e}")

    driver.disable()

if __name__ == "__main__":
    main()