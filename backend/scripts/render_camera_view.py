import pybullet as p
import pybullet_data
import numpy as np
import cv2  # optional, only if you want to view the image
offset_pos = [0.036, -0.006, 0.123]  # meters
offset_orn = p.getQuaternionFromEuler([0, 0, 0])
p.connect(p.GUI)
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.resetSimulation()
p.setGravity(0,0,-9.81)

robot = p.loadURDF("C:\\Users\\mattm\\OneDrive - Iowa State University\\Personal Projects\\ArctosArm\\ArctosArmController\\backend\\models\\urdf\\arctos_urdf.urdf", useFixedBase=True)
link_name = "Link_4_1"

# Find link index
link_index = None
for i in range(p.getNumJoints(robot)):
    info = p.getJointInfo(robot, i)
    child_link_name = info[12].decode('utf-8')
    if child_link_name == link_name:
        link_index = i
        break

if link_index is None:
    raise ValueError(f"Could not find link named {link_name}")

# Camera offset (in meters)
offset_pos = [0.036, -0.006, 0.123]
offset_orn = p.getQuaternionFromEuler([0, 0, 0])  # adjust later if camera faces wrong way

width, height = 640, 480
fov = 60
aspect = width / height
near, far = 0.01, 3.0

for _ in range(10000):
    p.stepSimulation()

    # Get link 4 world pose
    link_state = p.getLinkState(robot, link_index, computeForwardKinematics=True)
    link_pos, link_orn = link_state[0], link_state[1]

    # Compute camera world transform
    cam_pos, cam_orn = p.multiplyTransforms(link_pos, link_orn, offset_pos, offset_orn)

    # Convert quaternion to rotation matrix
    rot_matrix = p.getMatrixFromQuaternion(cam_orn)
    forward_vec = [rot_matrix[0], rot_matrix[3], rot_matrix[6]]  # X axis of camera frame
    up_vec = [rot_matrix[2], rot_matrix[5], rot_matrix[8]]       # Z axis of camera frame

    # Target point = camera position + small forward offset
    target_pos = [cam_pos[0] + 0.1 * forward_vec[0],
                  cam_pos[1] + 0.1 * forward_vec[1],
                  cam_pos[2] + 0.1 * forward_vec[2]]

    # Render camera view
    view_matrix = p.computeViewMatrix(cameraEyePosition=cam_pos,
                                       cameraTargetPosition=target_pos,
                                       cameraUpVector=up_vec)
    projection_matrix = p.computeProjectionMatrixFOV(fov, aspect, near, far)
    img_arr = p.getCameraImage(width, height,
                                viewMatrix=view_matrix,
                                projectionMatrix=projection_matrix)
