#!/usr/bin/env python3
"""
Test script for the AnalyticIKSolver class.
Tests inverse kinematics solving for various target poses.
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the path so we can import modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from core.ik.analytic import AnalyticIKSolver
import numpy as np

def test_ik_solver():
    """Test the IK solver with various target poses."""

    # Path to the URDF file
    urdf_path = backend_dir / "models" / "urdf" / "arctos_urdf.urdf"

    if not urdf_path.exists():
        print(f"Error: URDF file not found at {urdf_path}")
        return

    print(f"Testing IK solver with URDF: {urdf_path}")

    # Create the IK solver
    try:
        solver = AnalyticIKSolver(str(urdf_path))
        print("IK solver initialized successfully")
    except Exception as e:
        print(f"Failed to initialize IK solver: {e}")
        return

    # Test poses
    test_poses = [
        {
            "name": "Home position",
            "position": [0.0, 0.0, 0.0],
            "orientation": [0.0, 0.0, 0.0, 1.0]  # identity quaternion
        },
        {
            "name": "Forward reach",
            "position": [0.3, 0.0, 0.2],
            "orientation": [0.0, 0.0, 0.0, 1.0]
        },
        {
            "name": "Side reach",
            "position": [0.0, 0.3, 0.2],
            "orientation": [0.0, 0.0, 0.0, 1.0]
        },
        {
            "name": "High position",
            "position": [0.2, 0.1, 0.4],
            "orientation": [0.0, 0.0, 0.0, 1.0]
        },
        {
            "name": "Rotated pose",
            "position": [0.25, -0.15, 0.15],
            "orientation": [0.0, 0.0, 0.707, 0.707]  # 90 degrees around z
        }
    ]

    # Test each pose
    for i, pose in enumerate(test_poses):
        print(f"\n--- Test {i+1}: {pose['name']} ---")
        print(f"Target position: {pose['position']}")
        print(f"Target orientation: {pose['orientation']}")

        # Solve IK
        result = solver.solve(pose)

        print(f"Success: {result['success']}")
        print(f"Iterations: {result.get('iterations', 'N/A')}")
        print(f"Joint angles: {[f'{angle:.4f}' for angle in result['joints']]}")

        if 'error' in result:
            print(f"Error: {result['error']}")
        elif result['success']:
            # Test forward kinematics with the computed joint angles
            fk_result = solver.forward_kinematics(result['joints'])
            print(f"FK position: {[f'{coord:.4f}' for coord in fk_result['position']]}")
            print(f"FK orientation: {[f'{coord:.4f}' for coord in fk_result['orientation']]}")
            
            # Check if FK matches target (within tolerance)
            pos_error = np.linalg.norm(np.array(fk_result['position']) - np.array(pose['position']))
            print(f"Position error: {pos_error:.6f} meters")

    print("\n--- Forward Kinematics Test ---")
    # Test FK with some joint configurations
    test_joint_configs = [
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Home
        [0.5, 0.2, -0.3, 0.1, 0.0, 0.0],  # Some configuration
        [1.0, 0.5, 0.5, -0.5, 0.2, 0.3],  # Another configuration
    ]
    
    for i, joints in enumerate(test_joint_configs):
        print(f"\nFK Test {i+1}: Joints = {[f'{j:.2f}' for j in joints]}")
        fk_result = solver.forward_kinematics(joints)
        print(f"Position: {[f'{coord:.4f}' for coord in fk_result['position']]}")
        print(f"Orientation: {[f'{coord:.4f}' for coord in fk_result['orientation']]}")

    print("\n--- IK Solver Test Complete ---")

if __name__ == "__main__":
    test_ik_solver()