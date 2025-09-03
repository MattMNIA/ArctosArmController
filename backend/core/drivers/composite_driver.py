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

    def get_feedback(self):
        # Return feedback from the real arm (first driver)
        return self.drivers[0].get_feedback()

    def estop(self):
        for d in self.drivers: d.estop()
