import sys
sys.path.append('C:/Users/mattm/OneDrive - Iowa State University/Personal Projects/ArctosArm/ArctosArmController')

try:
    from backend.core.camera.stream import IPCameraStream
    from backend.core.camera.person_detector import PersonDetector
    
    # Try to create instances
    camera = IPCameraStream(url='http://192.168.50.254:81/stream')
    detector = PersonDetector(camera, detection_method='hog')
    print('Successfully imported and instantiated classes')
    
except Exception as e:
    print(f'Error: {type(e).__name__}: {str(e)}')
    import traceback
    traceback.print_exc()