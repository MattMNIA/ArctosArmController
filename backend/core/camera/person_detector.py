import cv2
import numpy as np
import time
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
import threading

# Use absolute import when file is run directly, otherwise try relative import

from stream import IPCameraStream



class PersonDetector:
    """
    Class for detecting people in video frames and calculating their positions.
    """
    
    # Detection methods
    METHOD_HOG = "hog"        # Faster but less accurate
    METHOD_DNN = "dnn"        # Slower but more accurate
    
    def __init__(self, 
                 camera_stream: IPCameraStream,
                 detection_method: str = METHOD_HOG,
                 confidence_threshold: float = 0.5,
                 process_every_n_frames: int = 3):
        """
        Initialize the person detector.
        
        Args:
            camera_stream: The camera stream object to get frames from
            detection_method: Detection method to use (hog or dnn)
            confidence_threshold: Minimum confidence for DNN detections (0.0 to 1.0)
            process_every_n_frames: Process every Nth frame to reduce CPU usage
        """
        self.camera_stream = camera_stream
        self.detection_method = detection_method
        self.confidence_threshold = confidence_threshold
        self.process_every_n_frames = max(1, process_every_n_frames)
        
        # Initialize detector based on selected method
        if detection_method == self.METHOD_HOG:
            # HOG detector with default people detector
            self.hog = cv2.HOGDescriptor()
            
            # In OpenCV 4.x, we need to convert the array to the right format
            try:
                # Try to use the default people detector
                detector = self.hog.getDefaultPeopleDetector()
                # Convert to the correct format if needed
                import numpy as np
                detector_array = np.array(detector)
                self.hog.setSVMDetector(detector_array)
            except Exception as e:
                print(f"Warning: Error setting up HOG detector: {e}")
                print("Will attempt to use default detector when detecting")
        elif detection_method == self.METHOD_DNN:
            # DNN detector (MobileNet SSD)
            model_dir = Path(__file__).parent / "models"
            model_dir.mkdir(exist_ok=True)
            
            # Check if model files exist, if not, they need to be downloaded
            prototxt_path = model_dir / "MobileNetSSD_deploy.prototxt"
            model_path = model_dir / "MobileNetSSD_deploy.caffemodel"
            
            if not prototxt_path.exists() or not model_path.exists():
                print("DNN model files not found. Please download them from:")
                print("https://github.com/chuanqi305/MobileNet-SSD/")
                print(f"and place them in {model_dir}")
                raise FileNotFoundError(f"Required model files not found in {model_dir}")
            
            self.net = cv2.dnn.readNetFromCaffe(
                str(prototxt_path),
                str(model_path)
            )
            
            # MobileNet SSD was trained on 300x300 images
            self.dnn_input_size = (300, 300)
            
            # Class labels MobileNet SSD was trained on
            self.class_labels = {15: "person"}  # We only care about the person class (ID 15)
        else:
            raise ValueError(f"Unknown detection method: {detection_method}")
        
        # Detection results
        self.last_detection_time = 0
        self.persons_detected = []  # List of bounding boxes
        self.processing_time = 0
        self.frame_count = 0
        
        # Background processing
        self.is_running = False
        self.thread = None
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """
        Start person detection in a background thread.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        if self.is_running:
            print("Person detector is already running.")
            return False
            
        if not self.camera_stream.is_running:
            print("Camera stream is not running. Starting camera stream first.")
            self.camera_stream.start()
        
        self.is_running = True
        self.thread = threading.Thread(target=self._process_frames, daemon=True)
        self.thread.start()
        print(f"Started person detection using {self.detection_method} method")
        return True
    
    def stop(self) -> None:
        """Stop the person detection thread."""
        self.is_running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Stopped person detection")
    
    def _detect_persons_hog(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect persons in a frame using HOG detector.
        
        Args:
            frame: Input frame
            
        Returns:
            List of (x, y, w, h) bounding boxes for detected persons
        """
        # Convert to grayscale for HOG
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect people
        boxes, weights = self.hog.detectMultiScale(
            gray,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
            useMeanshiftGrouping=False
        )
        
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in boxes]
    
    def _detect_persons_dnn(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect persons in a frame using DNN detector.
        
        Args:
            frame: Input frame
            
        Returns:
            List of (x, y, w, h) bounding boxes for detected persons
        """
        # Get frame dimensions
        (h, w) = frame.shape[:2]
        
        # Create a blob from the image
        blob = cv2.dnn.blobFromImage(
            cv2.resize(frame, self.dnn_input_size),
            0.007843, 
            self.dnn_input_size,
            127.5
        )
        
        # Set the blob as input to the network
        self.net.setInput(blob)
        
        # Forward pass through the network
        detections = self.net.forward()
        
        # Process detections
        boxes = []
        for i in range(detections.shape[2]):
            # Extract confidence
            confidence = detections[0, 0, i, 2]
            
            # Filter by confidence threshold
            if confidence > self.confidence_threshold:
                # Extract class ID
                class_id = int(detections[0, 0, i, 1])
                
                # Only keep person detections (class ID 15)
                if class_id == 15:  # person class
                    # Compute bounding box coordinates scaled to original image
                    box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    (start_x, start_y, end_x, end_y) = box.astype("int")
                    
                    # Extract width and height
                    width = end_x - start_x
                    height = end_y - start_y
                    
                    # Add to results
                    boxes.append((start_x, start_y, width, height))
        
        return boxes
    
    def _process_frames(self) -> None:
        """Background thread for processing frames and detecting persons."""
        frame_count = 0
        
        while self.is_running:
            # Get current frame from camera stream
            frame = self.camera_stream.get_frame()
            
            if frame is None:
                time.sleep(0.1)
                continue
                
            # Process only every Nth frame
            frame_count += 1
            if frame_count % self.process_every_n_frames != 0:
                continue
                
            # Detect persons
            start_time = time.time()
            
            try:
                if self.detection_method == self.METHOD_HOG:
                    persons = self._detect_persons_hog(frame)
                else:  # DNN method
                    persons = self._detect_persons_dnn(frame)
            except Exception as e:
                print(f"Error in person detection: {str(e)}")
                persons = []
                
            processing_time = time.time() - start_time
            
            # Update results with thread safety
            with self._lock:
                self.persons_detected = persons
                self.last_detection_time = time.time()
                self.processing_time = processing_time
                self.frame_count += 1
    
    def get_detections(self) -> List[Dict]:
        """
        Get the most recent person detections with position information.
        
        Returns:
            List of dictionaries with person detection info
        """
        frame = self.camera_stream.get_frame()
        if frame is None:
            return []
            
        frame_height, frame_width = frame.shape[:2]
        center_x, center_y = frame_width // 2, frame_height // 2
        
        with self._lock:
            persons = []
            
            for (x, y, w, h) in self.persons_detected:
                # Calculate the center point of the detected person
                person_center_x = x + (w // 2)
                person_center_y = y + (h // 2)
                
                # Calculate relative position from center (-1.0 to 1.0)
                rel_pos_x = (person_center_x - center_x) / (frame_width / 2)
                rel_pos_y = (person_center_y - center_y) / (frame_height / 2)
                
                # Calculate distance estimate (based on bounding box size)
                # Assuming height of box is inversely proportional to distance
                relative_size = h / frame_height
                distance_estimate = 1.0 / max(0.001, relative_size)  # Avoid division by zero
                
                persons.append({
                    "box": (x, y, w, h),
                    "center": (person_center_x, person_center_y),
                    "relative_position": (rel_pos_x, rel_pos_y),
                    "distance_estimate": distance_estimate,
                })
                
            return persons
    
    def get_status(self) -> dict:
        """
        Get current status of the person detector.
        
        Returns:
            dict: Status information
        """
        with self._lock:
            return {
                "running": self.is_running,
                "method": self.detection_method,
                "persons_count": len(self.persons_detected),
                "processing_time_ms": round(self.processing_time * 1000, 1),
                "frame_count": self.frame_count,
                "last_detection_time": self.last_detection_time,
            }
    
    def draw_detections(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw person detections on a frame.
        
        Args:
            frame: Input frame to draw on
            
        Returns:
            Frame with drawn detections
        """
        result_frame = frame.copy()
        
        # Get frame dimensions
        frame_height, frame_width = result_frame.shape[:2]
        center_x, center_y = frame_width // 2, frame_height // 2
        
        # Draw center crosshair
        cv2.line(result_frame, (center_x, 0), (center_x, frame_height), (0, 255, 255), 1)
        cv2.line(result_frame, (0, center_y), (frame_width, center_y), (0, 255, 255), 1)
        
        with self._lock:
            for (x, y, w, h) in self.persons_detected:
                # Draw bounding box
                cv2.rectangle(result_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                # Draw center point of the person
                person_center_x = x + (w // 2)
                person_center_y = y + (h // 2)
                cv2.circle(result_frame, (person_center_x, person_center_y), 5, (0, 0, 255), -1)
                
                # Draw line from center to person
                cv2.line(result_frame, (center_x, center_y), 
                         (person_center_x, person_center_y), (255, 0, 0), 2)
        
        # Add detector info
        status = self.get_status()
        cv2.putText(
            result_frame,
            f"Detector: {self.detection_method.upper()} | "
            f"Found: {status['persons_count']} | "
            f"Time: {status['processing_time_ms']}ms",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        
        return result_frame


# Example usage
if __name__ == "__main__":
    import sys
    import os
    
    # Add the project root directory to the Python path for imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
    if project_root not in sys.path:
        sys.path.append(project_root)
    
    # Import should work regardless of how the file is run
    from camera.stream import IPCameraStream
    
    # Create and start the camera stream
    camera = IPCameraStream(url="http://192.168.50.254:81/stream", fps_limit=30)
    camera.start()
    
    # Create and start person detector (using HOG method by default)
    detector = PersonDetector(camera, detection_method=PersonDetector.METHOD_HOG)
    detector.start()
    
    try:
        # Display video feed with person detections
        while True:
            frame = camera.get_frame()
            if frame is not None:
                # Draw detections on frame
                result = detector.draw_detections(frame)
                
                # Get person positions
                detections = detector.get_detections()
                for i, person in enumerate(detections):
                    pos = person["relative_position"]
                    dist = person["distance_estimate"]
                    print(f"Person {i+1}: Position ({pos[0]:.2f}, {pos[1]:.2f}), Distance: {dist:.2f}")
                
                # Display the frame
                cv2.imshow('Person Detector', result)
                
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
        detector.stop()
        camera.stop()
        cv2.destroyAllWindows()