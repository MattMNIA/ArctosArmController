import cv2
import threading
import time
from typing import Optional, Tuple
import numpy as np



class IPCameraStream:
    """
    A class to handle streaming video from an IP camera.
    Provides methods to access frames for computer vision processing.
    """
    
    def __init__(self, url: str = "http://192.168.50.254/", 
                 resolution: Optional[Tuple[int, int]] = None, 
                 fps_limit: Optional[int] = None):
        """
        Initialize the IP camera stream.
        
        Args:
            url: URL of the IP camera stream
            resolution: Optional tuple (width, height) to resize frames
            fps_limit: Optional FPS limit to avoid overloading the system
        """
        self.url = url
        self.resolution = resolution
        self.fps_limit = fps_limit
        
        # Stream control
        self.is_running = False
        self.thread = None
        
        # Frame data
        self.current_frame = None
        self.last_frame_time = 0
        self._lock = threading.Lock()
        
        # Stats
        self.fps = 0
        self.frame_count = 0
        self.connection_errors = 0
    
    def start(self) -> bool:
        """
        Start the video capture in a separate thread.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        if self.is_running:
            print("Stream is already running.")
            return False
        
        self.is_running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        print(f"Started camera stream from {self.url}")
        return True
    
    def stop(self) -> None:
        """Stop the video capture thread."""
        self.is_running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Stopped camera stream")
    
    def _update(self) -> None:
        """
        Continuously update the current frame from the IP camera.
        This method runs in a separate thread.
        """
        cap = cv2.VideoCapture(self.url)
        
        if not cap.isOpened():
            print(f"Error: Could not open video stream from {self.url}")
            self.is_running = False
            self.connection_errors += 1
            return
        
        frame_times = []
        last_time = time.time()
        
        while self.is_running:
            try:
                # If FPS limit is set, control the capture rate
                if self.fps_limit:
                    current_time = time.time()
                    elapsed = current_time - last_time
                    sleep_time = max(0, (1.0 / self.fps_limit) - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                
                success, frame = cap.read()
                current_time = time.time()
                
                if not success:
                    print("Failed to capture frame")
                    self.connection_errors += 1
                    # Try to reconnect
                    cap.release()
                    time.sleep(1.0)
                    cap = cv2.VideoCapture(self.url)
                    continue
                
                # Resize if needed
                if self.resolution:
                    frame = cv2.resize(frame, self.resolution)
                
                # Update FPS calculation (using a rolling window)
                frame_times.append(current_time)
                if len(frame_times) > 30:
                    frame_times.pop(0)
                
                if len(frame_times) > 1:
                    self.fps = len(frame_times) / (frame_times[-1] - frame_times[0])
                
                # Update current frame with thread safety
                with self._lock:
                    self.current_frame = frame.copy()
                    self.last_frame_time = current_time
                    self.frame_count += 1
                    
                last_time = current_time
                
            except Exception as e:
                print(f"Error in stream capture: {str(e)}")
                self.connection_errors += 1
                time.sleep(1.0)  # Avoid rapid reconnection attempts
        
        # Clean up
        cap.release()
    
    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get the most recent frame from the camera.
        
        Returns:
            np.ndarray or None: The current frame if available, or None
        """
        with self._lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None
    
    def get_status(self) -> dict:
        """
        Get current status of the camera stream.
        
        Returns:
            dict: Status information including FPS, frames captured, etc.
        """
        return {
            "running": self.is_running,
            "fps": round(self.fps, 1),
            "frame_count": self.frame_count,
            "connection_errors": self.connection_errors,
            "last_frame_time": self.last_frame_time,
        }


# Example usage
if __name__ == "__main__":
    # Create and start the camera stream
    stream = IPCameraStream(url="http://192.168.50.254:81/stream", fps_limit=30)
    stream.start()
    
    try:
        # Display video feed with simple FPS counter
        while True:
            frame = stream.get_frame()
            if frame is not None:
                # Add FPS text to the frame
                status = stream.get_status()
                cv2.putText(
                    frame,
                    f"FPS: {status['fps']:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                
                # Display the frame
                cv2.imshow('IP Camera Stream', frame)
                
                # Break loop on 'q' key
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                print("No frame available")
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        # Clean up
        stream.stop()
        cv2.destroyAllWindows()
