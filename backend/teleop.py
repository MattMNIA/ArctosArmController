import argparse
import utils.logger  # Import to trigger logging setup
from core.motion_service import MotionService
from core.teleop_controller import TeleopController
from core.drivers.can_driver import CanDriver
from core.drivers.pybullet_driver import PyBulletDriver
from core.drivers.composite_driver import CompositeDriver
from core.input.xbox_input import XboxController
from core.input.keyboard_input import KeyboardController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", choices=["xbox", "keyboard"], default="keyboard")
    args = parser.parse_args()
    pybullet_driver = PyBulletDriver(gui=True, urdf_path="C:\\Users\\mattm\\OneDrive - Iowa State University\\Personal Projects\\ArctosArm\\ArctosArmController\\backend\\models\\urdf\\arctos_urdf.urdf")
    can_driver = CanDriver()
    comp_driver = CompositeDriver([pybullet_driver, can_driver])
    
    # Connect and enable the driver directly
    comp_driver.connect()
    comp_driver.enable()
    
    # Choose input method
    if args.input == "xbox":
        controller = XboxController()
    else:
        controller = KeyboardController()

    # Create teleop controller with driver
    teleop_controller = TeleopController(controller, comp_driver)

    print(f"Running teleop with {args.input} input...")
    run_teleop_loop(teleop_controller)


def run_teleop_loop(teleop_controller):
    import time
    try:
        while True:
            teleop_controller.teleop_step()
            time.sleep(0.02)  # ~50Hz control loop
    except KeyboardInterrupt:
        print("Shutting down.")
        teleop_controller.driver.estop()
        teleop_controller.driver.disable()


if __name__ == "__main__":
    main()
