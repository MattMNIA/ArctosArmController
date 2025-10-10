import pybullet as p
import pybullet_data

p.connect(p.GUI)
p.setAdditionalSearchPath(pybullet_data.getDataPath())

robot = p.loadURDF("C:\\Users\\mattm\\OneDrive - Iowa State University\\Personal Projects\\ArctosArm\\ArctosArmController\\backend\\models\\urdf\\arctos_urdf.urdf", useFixedBase=True)
num_joints = p.getNumJoints(robot)

# Print all link names and IDs
link4_idx = None
for i in range(p.getNumJoints(robot)):
    info = p.getJointInfo(robot, i)
    child_link_name = info[12].decode('utf-8')
    if child_link_name == "Link_4_1":
        link4_idx = i
        print("Link_4_1 index:", link4_idx)

if link4_idx is None:
    raise ValueError("Link_4_1 not found in robot links.")

# Visualize its frame
def draw_axes(pos, orn):
    rot_matrix = p.getMatrixFromQuaternion(orn)
    forward_vec = [rot_matrix[0], rot_matrix[3], rot_matrix[6]]
    up_vec = [rot_matrix[2], rot_matrix[5], rot_matrix[8]]
    right_vec = [rot_matrix[1], rot_matrix[4], rot_matrix[7]]
    p.addUserDebugLine(pos, [pos[i] + 0.05 * forward_vec[i] for i in range(3)], [1, 0, 0], 2)  # X - red
    p.addUserDebugLine(pos, [pos[i] + 0.05 * up_vec[i] for i in range(3)], [0, 1, 0], 2)      # Y - green
    p.addUserDebugLine(pos, [pos[i] + 0.05 * right_vec[i] for i in range(3)], [0, 0, 1], 2)     # Z - blue

while True:
    link_state = p.getLinkState(robot, link4_idx, computeForwardKinematics=True)
    draw_axes(link_state[0], link_state[1])

