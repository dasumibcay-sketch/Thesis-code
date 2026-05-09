"""
Camera worker thread for BX53/BX53M-P Microscope Viewer
Handles video capture and frame processing in a separate thread
"""

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage
from config import CONFIG


class CameraWorker(QThread):
    """
    Worker thread for capturing and processing camera frames.
    
    Signals:
        frame_ready: Emits processed frame as QImage
        fps_updated: Emits current FPS value
        error_occurred: Emits error message string
        connected: Emits connection status
    """
    
    frame_ready = pyqtSignal(QImage)
    fps_updated = pyqtSignal(float)
    error_occurred = pyqtSignal(str)
    connected = pyqtSignal(bool)
    
    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self.cap = None
        self.is_running = False
        self.is_paused = False
        
        # FPS calculation
        self.frame_count = 0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        
        # Frame processing options
        self.apply_clahe = False
        self.apply_blur = False
        self.blur_kernel = (5, 5)
    
    def run(self):
        """Main thread execution."""
        try:
            self._initialize_camera()
            self.connected.emit(True)
            
            self.fps_timer.start(1000)
            self.is_running = True
            
            while self.is_running:
                if not self.is_paused:
                    ret, frame = self.cap.read()
                    
                    if ret:
                        # Process frame
                        processed_frame = self._process_frame(frame)
                        
                        # Convert to QImage
                        q_img = self._cv_to_qimage(processed_frame)
                        
                        # Emit signal
                        self.frame_ready.emit(q_img)
                        self.frame_count += 1
                    else:
                        self.error_occurred.emit("Failed to read frame from camera")
                
                self.msleep(30)  # ~30ms delay
        
        except Exception as e:
            self.error_occurred.emit(f"Camera error: {str(e)}")
            self.connected.emit(False)
        
        finally:
            self._cleanup()
    
    def _initialize_camera(self):
        """Initialize camera capture."""
        self.cap = cv2.VideoCapture(self.camera_index)
        
        if not self.cap.isOpened():
            raise Exception(f"Cannot open camera {self.camera_index}")
        
        # Set camera properties
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG.CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG.CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, CONFIG.CAMERA_FPS)
    
    def _process_frame(self, frame):
        """
        Process camera frame with various filters.
        
        Args:
            frame: Input frame (BGR format)
        
        Returns:
            Processed frame
        """
        # Convert BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        if self.apply_clahe:
            lab = cv2.cvtColor(frame, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            frame = cv2.merge([l, a, b])
            frame = cv2.cvtColor(frame, cv2.COLOR_LAB2RGB)
        
        # Apply Gaussian blur
        if self.apply_blur:
            frame = cv2.GaussianBlur(frame, self.blur_kernel, 0)
        
        return frame
    
    def _cv_to_qimage(self, cv_img):
        """
        Convert OpenCV image to QImage.
        
        Args:
            cv_img: OpenCV image (RGB)
        
        Returns:
            QImage object
        """
        height, width, channel = cv_img.shape
        bytes_per_line = 3 * width
        
        q_img = QImage(
            cv_img.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )
        
        return q_img.copy()
    
    def _update_fps(self):
        """Update FPS calculation."""
        fps = self.frame_count
        self.fps_updated.emit(float(fps))
        self.frame_count = 0
    
    def _cleanup(self):
        """Clean up resources."""
        self.fps_timer.stop()
        if self.cap:
            self.cap.release()
        self.is_running = False
    
    def pause(self):
        """Pause frame capture."""
        self.is_paused = True
    
    def resume(self):
        """Resume frame capture."""
        self.is_paused = False
    
    def stop(self):
        """Stop the worker thread."""
        self.is_running = False
        self.wait()
    
    def set_clahe(self, enabled):
        """Enable/disable CLAHE filter."""
        self.apply_clahe = enabled
    
    def set_blur(self, enabled, kernel=(5, 5)):
        """Enable/disable Gaussian blur filter."""
        self.apply_blur = enabled
        self.blur_kernel = kernel
    
    def capture_frame(self, filepath):
        """
        Capture current frame and save to file.
        
        Args:
            filepath: Path to save the frame
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.cap and not self.is_paused:
                ret, frame = self.cap.read()
                if ret:
                    cv2.imwrite(filepath, frame)
                    return True
        except Exception as e:
            self.error_occurred.emit(f"Capture error: {str(e)}")
        
        return False
