"""
Object tracking module for PPE detection.
Tracks workers across frames to maintain consistent IDs and monitor PPE compliance.
"""
import os
import sys
import yaml
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "video_processor", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


@dataclass
class TrackedObject:
    """Tracked object with history."""
    track_id: int
    class_name: str
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    frame_id: int
    timestamp: float
    age: int = 0
    lost_count: int = 0
    is_confirmed: bool = False
    bbox_history: List[Tuple[int, int, int, int]] = field(default_factory=list)
    velocity: Tuple[float, float] = (0.0, 0.0)


class PPETracker:
    """
    Multi-object tracker for PPE detection.
    Uses IoU-based matching with Kalman filter prediction.
    """
    
    def __init__(self, track_buffer: int = 30, match_thresh: float = 0.8,
                 high_thresh: float = 0.5, low_thresh: float = 0.1):
        """
        Initialize tracker.
        
        Args:
            track_buffer: Number of frames to keep lost tracks
            match_thresh: IoU threshold for matching detections to tracks
            high_thresh: Confidence threshold for high-confidence detections
            low_thresh: Confidence threshold for low-confidence detections
        """
        self.track_buffer = track_buffer or config['tracking']['track_buffer']
        self.match_thresh = match_thresh or config['tracking']['match_thresh']
        self.high_thresh = high_thresh or config['tracking']['track_high_thresh']
        self.low_thresh = low_thresh or config['tracking']['track_low_thresh']
        
        self.next_id = 1
        self.active_tracks: Dict[int, TrackedObject] = {}
        self.lost_tracks: Dict[int, TrackedObject] = {}
        self.frame_count = 0
    
    def update(self, detections: List, frame_id: int, timestamp: float) -> List[TrackedObject]:
        """
        Update tracker with new detections.
        
        Args:
            detections: List of Detection objects
            frame_id: Current frame ID
            timestamp: Frame timestamp
            
        Returns:
            List of tracked objects for current frame
        """
        self.frame_count = frame_id
        current_tracks = []
        
        # Separate high and low confidence detections
        high_conf_dets = [d for d in detections if d.confidence >= self.high_thresh]
        low_conf_dets = [d for d in detections if d.confidence >= self.low_thresh and d.confidence < self.high_thresh]
        
        # Match high confidence detections to active tracks
        matched, unmatched_dets, unmatched_tracks = self._match_tracks(
            self.active_tracks, high_conf_dets, frame_id
        )
        
        # Update matched tracks
        for track_id, det in matched:
            track = self.active_tracks[track_id]
            track.bbox = det.bbox
            track.confidence = det.confidence
            track.frame_id = frame_id
            track.timestamp = timestamp
            track.age += 1
            track.lost_count = 0
            track.is_confirmed = True
            track.bbox_history.append(det.bbox)
            if len(track.bbox_history) > 30:
                track.bbox_history.pop(0)
            track.velocity = self._calc_velocity(track.bbox_history)
            current_tracks.append(track)
        
        # Create new tracks from unmatched high confidence detections
        for det_idx in unmatched_dets:
            det = high_conf_dets[det_idx]
            if det.class_name == 'person':
                track = TrackedObject(
                    track_id=self.next_id,
                    class_name=det.class_name,
                    bbox=det.bbox,
                    confidence=det.confidence,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    age=1,
                    is_confirmed=False,
                    bbox_history=[det.bbox]
                )
                self.active_tracks[self.next_id] = track
                # Confirm immediately for persons
                track.is_confirmed = True
                current_tracks.append(track)
                self.next_id += 1
        
        # Try to match unmatched active tracks with low confidence detections
        if unmatched_tracks and low_conf_dets:
            lost_tracks_dict = {tid: self.active_tracks[tid] for tid in unmatched_tracks}
            matched2, unmatched_dets2, unmatched_tracks2 = self._match_tracks(
                lost_tracks_dict, low_conf_dets, frame_id
            )
            # Update matched low-confidence
            for track_id, det in matched2:
                track = self.active_tracks[track_id]
                track.bbox = det.bbox
                track.confidence = det.confidence
                track.frame_id = frame_id
                track.timestamp = timestamp
                track.age += 1
                track.lost_count = 0
                track.bbox_history.append(det.bbox)
                if len(track.bbox_history) > 30:
                    track.bbox_history.pop(0)
                current_tracks.append(track)
                unmatched_tracks.remove(track_id)
        
        # Move unmatched active tracks to lost
        for track_id in unmatched_tracks:
            if track_id in self.active_tracks:
                track = self.active_tracks[track_id]
                track.lost_count += 1
                # Predict position using velocity
                if len(track.bbox_history) >= 2:
                    vx, vy = track.velocity
                    last_bbox = track.bbox_history[-1]
                    predicted_bbox = (
                        int(last_bbox[0] + vx),
                        int(last_bbox[1] + vy),
                        int(last_bbox[2] + vx),
                        int(last_bbox[3] + vy)
                    )
                    track.bbox = predicted_bbox
                
                if track.lost_count <= self.track_buffer:
                    self.lost_tracks[track_id] = track
                
                del self.active_tracks[track_id]
        
        # Clean up old lost tracks
        expired_tracks = []
        for track_id, track in self.lost_tracks.items():
            track.lost_count += 1
            if track.lost_count > self.track_buffer:
                expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            del self.lost_tracks[track_id]
        
        # Add non-person tracked objects (PPE items)
        for det in high_conf_dets:
            if det.class_name != 'person':
                det.track_id = -1  # Will be assigned by association
                current_tracks.append(TrackedObject(
                    track_id=-1,
                    class_name=det.class_name,
                    bbox=det.bbox,
                    confidence=det.confidence,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    age=1,
                    is_confirmed=True,
                    bbox_history=[det.bbox]
                ))
        
        return current_tracks
    
    def _match_tracks(self, tracks: Dict[int, TrackedObject], detections: List,
                      frame_id: int) -> Tuple[List, List, List]:
        """
        Match tracks to detections using IoU.
        
        Returns:
            matched: List of (track_id, detection) pairs
            unmatched_detections: List of detection indices
            unmatched_tracks: List of track IDs
        """
        if not tracks or not detections:
            return [], list(range(len(detections))), list(tracks.keys())
        
        # Build IoU matrix
        iou_matrix = np.zeros((len(tracks), len(detections)), dtype=np.float32)
        track_ids = list(tracks.keys())
        
        for i, track_id in enumerate(track_ids):
            track = tracks[track_id]
            for j, det in enumerate(detections):
                iou_matrix[i, j] = self._compute_iou(track.bbox, det.bbox)
        
        # Hungarian matching (simplified: greedy matching)
        matched = []
        unmatched_dets = list(range(len(detections)))
        unmatched_tracks = list(range(len(track_ids)))
        
        # Sort by IoU descending
        indices = np.dstack(np.unravel_index(np.argsort(iou_matrix.ravel())[::-1], iou_matrix.shape))[0]
        
        for i, j in indices:
            if i in unmatched_tracks and j in unmatched_dets:
                if iou_matrix[i, j] >= self.match_thresh:
                    matched.append((track_ids[i], detections[j]))
                    unmatched_tracks.remove(i)
                    unmatched_dets.remove(j)
        
        # Convert track indices to IDs
        unmatched_track_ids = [track_ids[i] for i in unmatched_tracks]
        
        return matched, unmatched_dets, unmatched_track_ids
    
    @staticmethod
    def _compute_iou(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
        """Compute IoU between two bounding boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def _calc_velocity(history: List[Tuple[int, int, int, int]]) -> Tuple[float, float]:
        """Calculate velocity from bbox history."""
        if len(history) < 2:
            return (0.0, 0.0)
        
        # Average center displacement over last few frames
        recent = history[-5:] if len(history) >= 5 else history
        centers_x = [(b[0] + b[2]) / 2 for b in recent]
        centers_y = [(b[1] + b[3]) / 2 for b in recent]
        
        if len(centers_x) < 2:
            return (0.0, 0.0)
        
        vx = (centers_x[-1] - centers_x[0]) / len(centers_x)
        vy = (centers_y[-1] - centers_y[0]) / len(centers_y)
        
        return (vx, vy)
    
    def get_tracked_persons(self) -> List[TrackedObject]:
        """Get currently tracked persons."""
        return [t for t in self.active_tracks.values() 
                if t.class_name == 'person' and t.is_confirmed]
    
    def reset(self):
        """Reset tracker state."""
        self.active_tracks.clear()
        self.lost_tracks.clear()
        self.next_id = 1
        self.frame_count = 0