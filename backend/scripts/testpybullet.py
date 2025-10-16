import pybullet as p
p.connect(p.GUI)
p.loadURDF("backend/models/urdf/arctos_urdf.urdf", useFixedBase=True)
while True:
    p.stepSimulation()