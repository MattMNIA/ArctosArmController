import unittest
import pybullet as p
import time
import sys
import os
from pathlib import Path

# Add backend to path using relative path from this file
backend_path = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_path))

from core.drivers.pybullet_driver import PyBulletDriver

# URDF path relative to backend directory
URDF_PATH = backend_path / "models" / "urdf" / "arctos_urdf.urdf"


class TestPyBulletDriverGripper(unittest.TestCase):
    def setUp(self):
        self.driver = PyBulletDriver(str(URDF_PATH), gui=True)
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
