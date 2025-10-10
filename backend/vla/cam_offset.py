camera_offset = [0.05, 0.0, 0.02]   # 5 cm forward, 2 cm up
camera_rotation = [0, -90, 0]       # camera looking down -Y axis


import pybullet as p
import numpy as np

def get_camera_pose(robot_id, end_effector_link, offset_pos, offset_euler):
    link_state = p.getLinkState(robot_id, end_effector_link)
    base_pos, base_orn = link_state[0], link_state[1]

    # Convert offset to quaternion and rotate into world frame
    offset_quat = p.getQuaternionFromEuler(offset_euler)
    world_offset_pos, world_offset_orn = p.multiplyTransforms(
        base_pos, base_orn, offset_pos, offset_quat
    )

    return world_offset_pos, world_offset_orn

def get_eye_in_hand_image(robot_id, end_effector_link):
    # Replace these with your real mount offset values
    offset_pos = [0.05, 0, 0.02]        # meters
    offset_euler = [0, -np.pi/2, 0]     # looking downward
    
    cam_pos, cam_orn = get_camera_pose(robot_id, end_effector_link, offset_pos, offset_euler)

    rot_matrix = p.getMatrixFromQuaternion(cam_orn)
    forward_vec = [rot_matrix[0], rot_matrix[3], rot_matrix[6]]
    up_vec = [rot_matrix[2], rot_matrix[5], rot_matrix[8]]
    cam_target = [cam_pos[i] + 0.1 * forward_vec[i] for i in range(3)]

    view_matrix = p.computeViewMatrix(cam_pos, cam_target, up_vec)
    proj_matrix = p.computeProjectionMatrixFOV(fov=70, aspect=1.0, nearVal=0.01, farVal=2.0)

    width, height, rgb, depth, seg = p.getCameraImage(128, 128, view_matrix, proj_matrix)
    return rgb

