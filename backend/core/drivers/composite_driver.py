import threading
import time
from typing import List, Any

class CompositeDriver:
    def __init__(self, drivers):
        driver_order = ['CanDriver', 'PyBulletDriver', 'SimDriver']
   
        self.drivers = []
        for name in driver_order:
            for d in drivers:
                if d.__class__.__name__ == name:
                            self.drivers.append(d)
                            break

    def connect(self):
        for d in self.drivers: d.connect()

    def enable(self):
        for d in self.drivers: d.enable()

    def disable(self):
        for d in self.drivers: d.disable()

    def home(self):
        for d in self.drivers: d.home()

    def home_joints(self, joint_indices):
        for d in self.drivers: d.home_joints(joint_indices)

    def send_joint_targets(self, q, t_s):
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.send_joint_targets, args=(q, t_s))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    def open_gripper(self, force: float = 50.0) -> None:
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.open_gripper, args=(force,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()

    def close_gripper(self, force: float = 50.0) -> None:
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.close_gripper, args=(force,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()

    def set_gripper_position(self, position: float, force: float = 50.0) -> None:
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.set_gripper_position, args=(position, force))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()

    def start_joint_velocity(self, joint_index: int, scale: float) -> None:
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.start_joint_velocity, args=(joint_index, scale))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()

    def stop_joint_velocity(self, joint_index: int) -> None:
        threads = []
        for d in self.drivers:
            thread = threading.Thread(target=d.stop_joint_velocity, args=(joint_index,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()

    def get_feedback(self):
        # Return feedback from the real arm (first driver)
        return self.drivers[0].get_feedback()

    def estop(self):
        for d in self.drivers: d.estop()

    def handle_limits(self, feedback):
        # Aggregate limit handling from all drivers
        return any(d.handle_limits(feedback) for d in self.drivers)
