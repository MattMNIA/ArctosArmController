import argparse
from core.motion_service import MotionService
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
    motion_service = MotionService(pybullet_driver, loop_hz=50)
    motion_service.start()
    # Choose input method
    if args.input == "xbox":
        controller = XboxController()
    else:
        controller = KeyboardController()

    print(f"Running teleop with {args.input} input...")
    run_teleop_loop(motion_service, controller)


def run_teleop_loop(motion_service, controller):
    import time
    try:
        while True:
            commands = controller.get_commands()
            if commands:
                motion_service.teleop_step(controller)
            time.sleep(0.02)  # ~50Hz control loop
    except KeyboardInterrupt:
        print("Shutting down.")
        motion_service.driver.estop()


if __name__ == "__main__":
    main()
