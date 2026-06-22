"""
Video capture module for PPE tracking.
Supports camera feeds, RTSP streams, and video files.
"""
import os
import sys
import cv2
import time
import yaml
import threading
import queue
from typing import Optional, Generator
from dataclasses import dataclass
from pathlib import Path

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "video_processor", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


@dataclass
class Frame:
    """Single video frame."""
    image: any  # numpy array
    frame_id: int
    timestamp: float
    source: str = ""


class VideoCapture:
    """
    Threaded video capture for real-time frame acquisition.
    Supports USB cameras, RTSP streams, and video files.
    """
    
    def __init__(self, source: Optional[str] = None, buffer_size: int = 64):
        """
        Initialize video capture.
        
        Args:
            source: Camera index (int), RTSP URL (str), or video file path
            buffer_size: Maximum buffer size for frame queue
        """
        self.source = source or config['capture']['source']
        self.fps_target = config['capture']['fps']
        self.width = config['capture']['width']
        self.height = config['capture']['height']
        self.buffer_size = buffer_size or config['capture']['buffer_size']
        
        self.cap = None
        self.running = False
        self.thread = None
        self.frame_queue = queue.Queue(maxsize=self.buffer_size)
        self.current_frame = None
        self.frame_count = 0
        self.fps_actual = 0.0
        self._last_time = time.time()
        self._frame_times = []
    
    def open(self) -> bool:
        """Open the video source."""
        try:
            source_int = int(self.source)
            self.cap = cv2.VideoCapture(source_int)
            self.source_type = "camera"
        except (ValueError, TypeError):
            if str(self.source).startswith(('rtsp://', 'http://', 'https://')):
                self.cap = cv2.VideoCapture(self.source)
                self.source_type = "stream"
            else:
                self.cap = cv2.VideoCapture(self.source)
                self.source_type = "file"
        
        if not self.cap.isOpened():
            print(f"ERROR: Could not open video source: {self.source}")
            return False
        
        # Set camera properties
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps_target)
        
        # Get actual properties
        self.actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        print(f"Video source opened: {self.source}")
        print(f"  Resolution: {self.actual_width}x{self.actual_height}")
        print(f"  FPS: {self.actual_fps}")
        
        return True
    
    def start(self) -> bool:
        """Start capture thread."""
        if not self.cap and not self.open():
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print(f"Capture thread started (buffer: {self.buffer_size})")
        return True
    
    def _capture_loop(self):
        """Background thread for continuous frame capture."""
        frame_interval = 1.0 / self.fps_target if self.fps_target > 0 else 0
        last_frame_time = time.time()
        
        while self.running:
            try:
                ret, frame = self.cap.read()
                
                if not ret:
                    if self.source_type == "file":
                        print("End of video file reached")
                        self.running = False
                        break
                    else:
                        # Reconnect for streams
                        print("Lost connection, reconnecting...")
                        self.cap.release()
                        time.sleep(1)
                        self.open()
                        continue
                
                self.frame_count += 1
                timestamp = time.time()
                
                # Calculate FPS
                self._frame_times.append(timestamp)
                if len(self._frame_times) > 30:
                    self._frame_times.pop(0)
                if len(self._frame_times) > 1:
                    self.fps_actual = len(self._frame_times) / (self._frame_times[-1] - self._frame_times[0])
                
                # Create Frame object
                video_frame = Frame(
                    image=frame,
                    frame_id=self.frame_count,
                    timestamp=timestamp,
                    source=str(self.source)
                )
                
                # Store current frame (for get_latest_frame)
                self.current_frame = video_frame
                
                # Put in queue (non-blocking, drop oldest if full)
                try:
                    self.frame_queue.put_nowait(video_frame)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait(video_frame)
                    except queue.Empty:
                        pass
                
                # Rate limiting for file playback
                if self.source_type == "file" and self.fps_target > 0:
                    elapsed = time.time() - last_frame_time
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    last_frame_time = time.time()
            
            except Exception as e:
                print(f"Capture error: {e}")
                time.sleep(0.1)
    
    def read(self) -> Optional[Frame]:
        """
        Read the next frame from queue.
        
        Returns:
            Frame or None if no frame available
        """
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_latest_frame(self) -> Optional[Frame]:
        """Get the most recent frame, discarding older ones."""
        frame = None
        while not self.frame_queue.empty():
            try:
                frame = self.frame_queue.get_nowait()
            except queue.Empty:
                break
        return frame or self.current_frame
    
    def get_current_frame(self) -> Optional[Frame]:
        """Get the current frame without blocking."""
        return self.current_frame
    
    def release(self):
        """Release the capture device and stop thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        print("Video capture released")
    
    @property
    def is_running(self) -> bool:
        """Check if capture is active."""
        return self.running and self.thread and self.thread.is_alive()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


if __name__ == "__main__":
    # Quick test
    cap = VideoCapture(source=0)
    if cap.open():
        cap.start()
        time.sleep(2)
        frame = cap.get_latest_frame()
        if frame:
            print(f"Frame captured: {frame.image.shape}, ID: {frame.frame_id}")
        cap.release()
    else:
        print("Failed to open camera")