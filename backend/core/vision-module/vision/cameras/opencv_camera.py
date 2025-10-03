from .base_camera import BaseCamera
import cv2

class OpenCVCamera(BaseCamera):
    def __init__(self, camera_index: int = 0, resolution: Tuple[int, int] = (640, 480), frame_rate: int = 30):
        super().__init__()
        self.camera_index = camera_index
        self.resolution = resolution
        self.frame_rate = frame_rate
        self.capture = None

    def start(self) -> None:
        self.capture = cv2.VideoCapture(self.camera_index)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.capture.set(cv2.CAP_PROP_FPS, self.frame_rate)

    def stop(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def get_frame(self) -> Optional[np.ndarray]:
        if self.capture is None:
            return None
        ret, frame = self.capture.read()
        if not ret:
            return None
        return frame

    def is_opened(self) -> bool:
        return self.capture is not None and self.capture.isOpened()