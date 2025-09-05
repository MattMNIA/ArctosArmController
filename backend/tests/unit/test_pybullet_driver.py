import unittest
import pybullet as p
import time
import sys
import os

# Add backend to path using absolute path
backend_path = r'c:\Users\mattm\OneDrive - Iowa State University\Personal Projects\ArctosArm\ArctosArmController\backend'
sys.path.insert(0, backend_path)

from core.drivers.pybullet_driver import PyBulletDriver

class TestPyBulletDriverGripper(unittest.TestCase):
    def setUp(self):
        urdf_path = "c:\\Users\\mattm\\OneDrive - Iowa State University\\Personal Projects\\ArctosArm\\ArctosArmController\\backend\\models\\urdf\\arctos_urdf.urdf"
        self.driver = PyBulletDriver(urdf_path, gui=True)
        self.driver.connect()
        self.driver.enable()

    def tearDown(self):
        self.driver.disable()

    def test_open_gripper(self):
        self.driver.open_gripper()
        # Step simulation to allow movement
        for _ in range(100):
            p.stepSimulation()
            time.sleep(0.01)
        # Check positions
        left_state = p.getJointState(self.driver.robot_id, 7)
        right_state = p.getJointState(self.driver.robot_id, 8)
        time.sleep(5)
        self.assertAlmostEqual(left_state[0], 0.0, places=2)
        self.assertAlmostEqual(right_state[0], 0.0, places=2)

    def test_close_gripper(self):
        self.driver.close_gripper()
        # Step simulation
        for _ in range(100):
            p.stepSimulation()
            time.sleep(0.01)
        # Check positions
        left_state = p.getJointState(self.driver.robot_id, 7)
        right_state = p.getJointState(self.driver.robot_id, 8)
        time.sleep(5)

        self.assertAlmostEqual(left_state[0], 0.15, places=2)
        self.assertAlmostEqual(right_state[0], 0.15, places=2)

    def test_set_gripper_position(self):
        position = 0.1
        self.driver.set_gripper_position(position)
        # Step simulation
        for _ in range(100):
            p.stepSimulation()
            time.sleep(0.01)
        # Check positions
        left_state = p.getJointState(self.driver.robot_id, 7)
        right_state = p.getJointState(self.driver.robot_id, 8)
        time.sleep(5)

        self.assertAlmostEqual(left_state[0], position, places=2)
        self.assertAlmostEqual(right_state[0], position, places=2)

if __name__ == '__main__':
    unittest.main()
