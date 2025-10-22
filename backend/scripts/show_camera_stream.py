import sys
import cv2
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.vision.cameras.ip_camera import IPCamera

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_camera_stream.py <camera_url>")
        sys.exit(1)

    camera_url = sys.argv[1]

    try:
        cam = IPCamera(camera_url)
        if not cam.is_opened():
            print("Failed to open camera")
            sys.exit(1)

        print("Press 'q' to quit the stream.")

        while True:
            ret, frame = cam.read()
            if ret:
                cv2.imshow('Camera Stream', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cam.release()
        cv2.destroyAllWindows()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)