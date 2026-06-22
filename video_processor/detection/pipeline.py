"""
Detection pipeline that integrates capture, detection, tracking, and violation analysis.
"""
import os
import sys
import yaml
import cv2
import time
import json
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from threading import Lock
import logging

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import project modules
from video_processor.capture.capture import VideoCapture, Frame
from model.inference.detector import PPEDetector, DetectionResult, Detection
from video_processor.tracking.tracker import PPETracker, TrackedObject

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "video_processor", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


@dataclass
class PipelineFrame:
    """Processed frame data from the pipeline."""
    frame_id: int
    timestamp: float
    image: np.ndarray
    detections: List[Detection]
    tracked_objects: List[TrackedObject]
    violations: Dict[str, List[Detection]]
    person_count: int
    fps: float
    inference_time_ms: float
    total_process_time_ms: float


class DetectionPipeline:
    """
    End-to-end detection pipeline: capture -> detect -> track -> analyze violations.
    """
    
    def __init__(self, source: Optional[str] = None, 
                 model_path: Optional[str] = None,
                 enable_tracking: bool = True,
                 skip_frames: int = 2):
        """
        Initialize the detection pipeline.
        
        Args:
            source: Video source (camera index, RTSP URL, file path)
            model_path: Path to trained model weights
            enable_tracking: Whether to enable object tracking
            skip_frames: Process every Nth frame (for performance)
        """
        self.source = source
        self.model_path = model_path
        self.enable_tracking = enable_tracking and config['tracking']['enabled']
        self.skip_frames = skip_frames or config['detection']['skip_frames']
        
        # Components
        self.capture = None
        self.detector = None
        self.tracker = None
        
        # State
        self.running = False
        self.paused = False
        self.frame_count = 0
        self.processed_count = 0
        self.fps = 0.0
        self._lock = Lock()
        self._callbacks = []
        
        # Statistics
        self.stats = {
            'total_frames': 0,
            'processed_frames': 0,
            'total_violations': 0,
            'violations_by_type': {},
            'avg_inference_ms': 0.0,
            'avg_process_ms': 0.0,
            'person_count_history': [],
        }
    
    def initialize(self) -> bool:
        """Initialize all pipeline components."""
        print("Initializing detection pipeline...")
        
        # 1. Initialize capture
        self.capture = VideoCapture(source=self.source)
        if not self.capture.open():
            print("ERROR: Failed to open video source")
            return False
        
        # 2. Initialize detector
        try:
            self.detector = PPEDetector(model_path=self.model_path)
        except Exception as e:
            print(f"ERROR: Failed to initialize detector: {e}")
            return False
        
        # 3. Initialize tracker
        if self.enable_tracking:
            self.tracker = PPETracker()
            print("Tracker initialized")
        
        print("Pipeline initialized successfully")
        return True
    
    def start(self):
        """Start the pipeline."""
        if not self.capture:
            if not self.initialize():
                return
        
        self.running = True
        self.capture.start()
        print("Pipeline started")
    
    def stop(self):
        """Stop the pipeline."""
        self.running = False
        if self.capture:
            self.capture.release()
        print("Pipeline stopped")
    
    def pause(self):
        """Pause processing."""
        self.paused = True
    
    def resume(self):
        """Resume processing."""
        self.paused = False
    
    def process_frame(self, frame: Frame) -> Optional[PipelineFrame]:
        """
        Process a single frame through the pipeline.
        
        Args:
            frame: Input video frame
            
        Returns:
            Processed pipeline frame or None
        """
        if frame is None or frame.image is None:
            return None
        
        start_time = time.time()
        
        # 1. Run detection
        detection_result = self.detector.detect(frame.image)
        detections = detection_result.detections
        
        # 2. Run tracking
        tracked_objects = []
        if self.enable_tracking and self.tracker:
            tracked_objects = self.tracker.update(
                detections, frame.frame_id, frame.timestamp
            )
            # Assign track IDs to detections
            for track in tracked_objects:
                if track.track_id > 0:
                    for det in detections:
                        iou = DetectionResult._calculate_iou(det.bbox, track.bbox)
                        if iou > 0.5:
                            det.track_id = track.track_id
        
        # 3. Analyze PPE violations
        violations = detection_result.get_ppe_violations()
        
        # 4. Count persons
        persons = [d for d in detections if d.class_name == 'person']
        person_count = len(persons)
        
        # Calculate times
        total_time = (time.time() - start_time) * 1000  # ms
        
        # Update stats
        with self._lock:
            self.stats['total_frames'] += 1
            self.stats['processed_frames'] += 1
            self.stats['avg_inference_ms'] = (
                self.stats['avg_inference_ms'] * 0.95 + detection_result.inference_time_ms * 0.05
            )
            self.stats['avg_process_ms'] = (
                self.stats['avg_process_ms'] * 0.95 + total_time * 0.05
            )
            
            for vtype, vlist in violations.items():
                self.stats['total_violations'] += len(vlist)
                self.stats['violations_by_type'][vtype] = (
                    self.stats['violations_by_type'].get(vtype, 0) + len(vlist)
                )
            
            self.stats['person_count_history'].append(person_count)
            if len(self.stats['person_count_history']) > 100:
                self.stats['person_count_history'].pop(0)
        
        # Build pipeline frame
        pipeline_frame = PipelineFrame(
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            image=frame.image,
            detections=detections,
            tracked_objects=tracked_objects,
            violations=violations,
            person_count=person_count,
            fps=self.capture.fps_actual if self.capture else 0,
            inference_time_ms=detection_result.inference_time_ms,
            total_process_time_ms=total_time
        )
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(pipeline_frame)
            except Exception as e:
                print(f"Callback error: {e}")
        
        return pipeline_frame
    
    def run(self):
        """Main processing loop."""
        if not self.running:
            self.start()
        
        print("Entering main processing loop...")
        frame_skip_counter = 0
        
        while self.running:
            if self.paused:
                time.sleep(0.01)
                continue
            
            # Get frame from capture
            frame = self.capture.get_latest_frame()
            
            if frame is None:
                time.sleep(0.001)
                continue
            
            frame_skip_counter += 1
            
            # Skip frames for performance
            if frame_skip_counter % (self.skip_frames + 1) != 0:
                continue
            
            # Process frame
            result = self.process_frame(frame)
            
            if result is not None:
                self.fps = result.fps
                self.processed_count += 1
            
            # Check for end of video file
            if self.capture.source_type == "file" and not self.capture.is_running:
                print("End of video reached")
                break
    
    def run_async(self) -> 'DetectionPipeline':
        """Run pipeline in a background thread."""
        import threading
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return self
    
    def get_annotated_frame(self, pipeline_frame: PipelineFrame) -> np.ndarray:
        """Create annotated visualization frame."""
        if pipeline_frame is None:
            return None
        
        image = pipeline_frame.image.copy()
        h, w = image.shape[:2]
        
        # Draw detections
        image = self.detector.draw_detections(
            image,
            DetectionResult(detections=pipeline_frame.detections),
            show_conf=False,
            show_track=True
        )
        
        # Draw violations
        image = self.detector.draw_violations(image, pipeline_frame.violations)
        
        # Draw status overlay
        image = self.detector.draw_ppe_status(
            image, pipeline_frame.violations, pipeline_frame.person_count
        )
        
        # Draw FPS and processing info
        cv2.putText(image, f"FPS: {pipeline_frame.fps:.1f}", (w - 180, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 2)
        cv2.putText(image, f"Process: {pipeline_frame.total_process_time_ms:.0f}ms", 
                   (w - 180, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 200, 100), 1)
        
        return image
    
    def register_callback(self, callback: Callable[[PipelineFrame], None]):
        """Register a callback for processed frames."""
        self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable):
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def get_stats(self) -> Dict:
        """Get pipeline statistics."""
        with self._lock:
            return dict(self.stats)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    # Quick test
    pipeline = DetectionPipeline(source=0)
    if pipeline.initialize():
        print("Pipeline test: OK")
        print(f"Tracking enabled: {pipeline.enable_tracking}")
        print(f"Skip frames: {pipeline.skip_frames}")
        pipeline.stop()