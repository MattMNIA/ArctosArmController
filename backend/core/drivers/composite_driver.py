class CompositeDriver:
    def __init__(self, drivers):
        self.drivers = drivers

    def connect(self):
        for d in self.drivers: d.connect()

    def enable(self):
        for d in self.drivers: d.enable()

    def disable(self):
        for d in self.drivers: d.disable()

    def home(self):
        for d in self.drivers: d.home()

    def send_joint_targets(self, q, t_s):
        for d in self.drivers: d.send_joint_targets(q, t_s)

    def open_gripper(self, force: float = 50.0) -> None:
        for d in self.drivers: d.open_gripper(force)

    def close_gripper(self, force: float = 50.0) -> None:
        for d in self.drivers: d.close_gripper(force)

    def set_gripper_position(self, position: float, force: float = 50.0) -> None:
        for d in self.drivers: d.set_gripper_position(position, force)
        
    def grasp_object(self, force: float = 100.0) -> None:
        for d in self.drivers: d.grasp_object(force)

    def get_feedback(self):
        # Return feedback from the real arm (first driver)
        return self.drivers[0].get_feedback()

    def estop(self):
        for d in self.drivers: d.estop()

    def handle_limits(self, feedback):
        # Aggregate limit handling from all drivers
        return any(d.handle_limits(feedback) for d in self.drivers)
