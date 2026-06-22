import os
import sys
import yaml
import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import time

try:
    import torch
    original_load = torch.load
    def patched_load(*args, **kwargs):
        kwargs['weights_only'] = False
        return original_load(*args, **kwargs)
    torch.load = patched_load
except Exception:
    pass

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "model", "ppe_config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


@dataclass
class Detection:
    """Single detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    track_id: Optional[int] = None


@dataclass
class DetectionResult:
    """Detection results for a single frame."""
    detections: List[Detection] = field(default_factory=list)
    frame_id: int = 0
    timestamp: float = 0.0
    fps: float = 0.0
    inference_time_ms: float = 0.0
    
    def get_ppe_violations(self) -> Dict[str, List[Detection]]:
        """
        Check for PPE violations per person.
        Returns dict of violation_type -> list of violating persons.
        """
        violations = {}
        
        persons = [d for d in self.detections if d.class_name == 'person']
        if not persons:
            return violations
        
        # Pre-slice non-person detections once to avoid repeated filtering cost.
        non_person_dets = [d for d in self.detections if d.class_name != 'person']

        for person in persons:
            # Find PPE items associated with this person (within bbox proximity)
            has_helmet = False
            has_gloves = False
            has_shoes = False
            has_suit = False

            # Early exit once we found everything; saves time on dense scenes.
            # Also filter by coarse bbox overlap before computing IoU (cheaper).
            px1, py1, px2, py2 = person.bbox
            for det in non_person_dets:
                if has_helmet and has_gloves and has_shoes and has_suit:
                    break

                dx1, dy1, dx2, dy2 = det.bbox

                # Coarse overlap check: if there is no intersection, IoU will be 0.
                if dx2 <= px1 or dx1 >= px2 or dy2 <= py1 or dy1 >= py2:
                    continue

                # Calculate IoU with person bbox to check association
                iou = self._calculate_iou(person.bbox, det.bbox)
                if iou < 0.01:
                    continue

                if det.class_name == 'helmet':
                    has_helmet = True
                elif det.class_name == 'hands':
                    has_gloves = True
                elif det.class_name == 'shoes':
                    has_shoes = True
                elif det.class_name == 'safety_suit':
                    has_suit = True

            if not has_helmet:
                violations.setdefault('no_helmet', []).append(person)
            if not has_gloves:
                violations.setdefault('no_gloves', []).append(person)
            if not has_shoes:
                violations.setdefault('no_shoes', []).append(person)
            if not has_suit:
                violations.setdefault('no_safety_suit', []).append(person)

        return violations
    
    @staticmethod
    def _calculate_iou(box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
        """Calculate IoU between two bounding boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0


class PPEDetector:
    """
    PPE Detection engine using YOLOv8.
    Handles model loading, inference, and post-processing.
    """
    
    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None,
                 conf_threshold: Optional[float] = None, iou_threshold: Optional[float] = None):
        """
        Initialize the PPE detector.

        Args:
            model_path: Path to model weights. If None, resolves from config paths safely (offline/local only).
            device: Device to run inference on ('cpu', 'cuda:0', 'mps')
            conf_threshold: Confidence threshold for detections
            iou_threshold: IoU threshold for NMS
        """
        self.config = config

        self.device = device or self.config['model']['device']
        self.conf_threshold = conf_threshold or self.config['model']['conf_threshold']
        self.iou_threshold = iou_threshold or self.config['model']['iou_threshold']

        # Load model (offline/local only)
        if model_path:
            resolved_model_path = model_path
        else:
            weights_root = self.config.get("paths", {}).get("weights")
            if not weights_root:
                raise ValueError("config['paths']['weights'] is missing; cannot resolve model weights")

            # Support multiple weight layouts.
            # Your repo may have:
            # - model/weights/ppe_detection/weights/best.pt (older training output)
            # - model/weights/ppe.pt (single file export)
            # - model/weights/best.pt (generic)
            candidate_paths = [
                os.path.join(weights_root, "ppe_detection", "weights", "best.pt"),
                os.path.join(weights_root, "ppe.pt"),
                os.path.join(weights_root, "best.pt"),
            ]

            # Choose first path that exists and is non-empty.
            resolved_model_path = None
            for p in candidate_paths:
                try:
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        resolved_model_path = p
                        break
                except OSError:
                    continue

            if resolved_model_path is None:
                # Keep the failure explicit so video upload jobs show actionable error.
                raise FileNotFoundError(
                    "Offline mode: no valid (non-empty) local weights found. Tried:\n"
                    + "\n".join(f" - {p}" for p in candidate_paths)
                )

        self._resolved_model_path = resolved_model_path
        model_path = self._resolved_model_path

        # Load model
        self._load_model(model_path)

        # Class mapping will be loaded from the model itself (ultralytics `model.names`).
        # NOTE: `self.class_names` is used later to translate cls_id -> human label.
        self.class_names = getattr(self.model, "names", {}) or {}

    def _load_model(self, model_path: str):
        """Load YOLOv8 model (OFFLINE/LOCAL ONLY)."""
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("ultralytics is required. Install with: pip install ultralytics")

        # OFFLINE guarantee:
        # - If caller provides a bare filename like "yolov8m.pt", Ultralytics may attempt download.
        # - This repo must never trigger downloads; fail fast if local weights are not present.
        is_bare_filename = os.path.basename(model_path) == model_path and not any(
            sep in model_path for sep in (os.sep, "/", "\\")
        )

        if is_bare_filename and not os.path.exists(model_path):
            raise FileNotFoundError(
                "Offline mode: refusing to load a bare/remote model reference "
                f"('{model_path}'). Provide an explicit local file path to a .pt under "
                "config['paths']['weights'] (e.g. model/weights/.../best.pt) and/or pass model_path explicitly."
            )

        # Only accept local filesystem paths.
        if not os.path.exists(model_path):
            # Do not silently fall back to any arbitrary .pt elsewhere.
            # (This avoids accidentally loading an unexpected file and keeps startup deterministic.)
            raise FileNotFoundError(
                f"Offline mode: model weights not found at: {model_path}. "
                "Provide a trained weights .pt under config['paths']['weights'] "
                "(expected by config/model/ppe_config.yaml) and ensure it exists."
            )

        print(f"Loading detection model from local path: {model_path}")
        self.model = YOLO(model_path)

        # Warm up is intentionally skipped here to reduce startup cost/timeouts.
        # First real inference will compile as needed.
        print(f"Model loaded on device: {self.device}")

    
    def detect(self, image: np.ndarray, conf_threshold: Optional[float] = None,
               iou_threshold: Optional[float] = None) -> DetectionResult:
        """
        Run detection on a single frame.
        
        Args:
            image: Input image (BGR format, as from OpenCV)
            conf_threshold: Override confidence threshold
            iou_threshold: Override IoU threshold
            
        Returns:
            DetectionResult with all detections
        """
        if image is None or image.size == 0:
            return DetectionResult()
        
        conf = conf_threshold or self.conf_threshold
        iou = iou_threshold or self.iou_threshold
        
        start_time = time.time()
        
        # Run inference
        results = self.model(
            image,
            conf=conf,
            iou=iou,
            imgsz=self.config['model']['input_size'],
            device=self.device,
            verbose=False
        )
        
        inference_time = (time.time() - start_time) * 1000  # ms
        
        # Parse results
        detections = []
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i].item())
                conf_val = float(boxes.conf[i].item())
                xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                
                if cls_id in self.class_names:
                    detection = Detection(
                        class_id=cls_id,
                        class_name=self.class_names[cls_id],
                        confidence=conf_val,
                        bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
                    )
                    detections.append(detection)
        
        return DetectionResult(
            detections=detections,
            inference_time_ms=inference_time
        )
    
    def detect_batch(self, images: List[np.ndarray], batch_size: int = 4,
                     conf_threshold: Optional[float] = None,
                     iou_threshold: Optional[float] = None) -> List[DetectionResult]:
        """
        Run detection on a batch of frames.
        
        Args:
            images: List of input images
            batch_size: Batch size for inference
            conf_threshold: Override confidence threshold
            iou_threshold: Override IoU threshold
            
        Returns:
            List of DetectionResult objects
        """
        conf = conf_threshold or self.conf_threshold
        iou = iou_threshold or self.iou_threshold
        
        all_results = []
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            
            # Run inference on batch
            results = self.model(
                batch,
                conf=conf,
                iou=iou,
                imgsz=self.config['model']['input_size'],
                device=self.device,
                verbose=False
            )
            
            for j, result in enumerate(results):
                detections = []
                if result.boxes is not None:
                    boxes = result.boxes
                    for k in range(len(boxes)):
                        cls_id = int(boxes.cls[k].item())
                        conf_val = float(boxes.conf[k].item())
                        xyxy = boxes.xyxy[k].cpu().numpy().astype(int)
                        
                        if cls_id in self.class_names:
                            detection = Detection(
                                class_id=cls_id,
                                class_name=self.class_names[cls_id],
                                confidence=conf_val,
                                bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3]))
                            )
                            detections.append(detection)
                
                all_results.append(DetectionResult(detections=detections))
        
        return all_results
    
    def draw_detections(self, image: np.ndarray, result: DetectionResult,
                        show_conf: bool = True, show_track: bool = True,
                        line_width: int = 2) -> np.ndarray:
        """
        Draw detection results on image.
        
        Args:
            image: Input image
            result: DetectionResult to draw
            show_conf: Show confidence scores
            show_track: Show track IDs
            line_width: Width of bounding box lines
            
        Returns:
            Image with visualizations
        """
        colors = {
            'person': (0, 255, 0),      # Green
            'helmet': (255, 0, 0),      # Blue
            'hands': (0, 255, 255),     # Yellow
            'shoes': (255, 0, 255),     # Purple
            'safety_suit': (0, 165, 255), # Orange
            'tools': (255, 255, 0),     # Cyan
        }
        
        img = image.copy()
        
        for det in result.detections:
            x1, y1, x2, y2 = det.bbox
            color = colors.get(det.class_name, (255, 255, 255))
            
            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), color, line_width)
            
            # Build label
            label = det.class_name
            if show_conf:
                label += f" {det.confidence:.2f}"
            if show_track and det.track_id is not None:
                label += f" ID:{det.track_id}"
            
            # Draw label background
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(img, (x1, y1 - text_h - 8), (x1 + text_w + 8, y1), color, -1)
            
            # Draw label text
            text_color = (0, 0, 0) if np.mean(color) > 128 else (255, 255, 255)
            cv2.putText(img, label, (x1 + 4, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 2)
        
        return img
    
    def draw_violations(self, image: np.ndarray, violations: Dict[str, List[Detection]],
                        line_width: int = 3) -> np.ndarray:
        """
        Highlight PPE violations with red borders.
        
        Args:
            image: Input image
            violations: Dict of violation_type -> list of persons
            line_width: Width of violation border
            
        Returns:
            Image with violation highlights
        """
        img = image.copy()
        
        violation_colors = {
            'no_helmet': (0, 0, 255),      # Red
            'no_gloves': (0, 0, 200),      # Dark Red
            'no_shoes': (0, 0, 180),       # 
            'no_safety_suit': (0, 0, 220), #
        }
        
        for violation_type, persons in violations.items():
            color = violation_colors.get(violation_type, (0, 0, 255))
            
            for person in persons:
                x1, y1, x2, y2 = person.bbox
                # Draw thick red border
                cv2.rectangle(img, (x1, y1), (x2, y2), color, line_width * 2)
                
                # Draw violation label
                label = violation_type.replace('_', ' ').upper()
                (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(img, (x1, y2 - text_h - 10), (x1 + text_w + 10, y2), color, -1)
                cv2.putText(img, label, (x1 + 5, y2 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        return img
    
    def draw_ppe_status(self, image: np.ndarray, violations: Dict[str, List[Detection]],
                        person_count: int) -> np.ndarray:
        """
        Draw PPE compliance status overlay on image.
        
        Args:
            image: Input image
            violations: Dict of PPE violations
            person_count: Total number of persons detected
            
        Returns:
            Image with status overlay
        """
        img = image.copy()
        h, w = img.shape[:2]
        
        # Semi-transparent overlay
        overlay = img.copy()
        cv2.rectangle(overlay, (10, 10), (350, 160), (0, 0, 0), -1)
        img = cv2.addWeighted(overlay, 0.5, img, 0.5, 0)
        
        # Status text
        y_offset = 40
        cv2.putText(img, f"PPE Compliance Status", (20, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        y_offset += 30
        cv2.putText(img, f"Workers: {person_count}", (20, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        violation_count = sum(len(v) for v in violations.values())
        status_color = (0, 255, 0) if violation_count == 0 else (0, 0, 255)
        status_text = "ALL COMPLIANT" if violation_count == 0 else f"{violation_count} VIOLATION(S)"
        
        y_offset += 25
        cv2.putText(img, f"Status: {status_text}", (20, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2)
        
        # List violations
        y_offset += 25
        for vtype, persons in violations.items():
            label = vtype.replace('_', ' ').title()
            cv2.putText(img, f"  {label}: {len(persons)} worker(s)", (20, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 200), 1)
            y_offset += 22
        
        return img


if __name__ == "__main__":
    # Quick test
    detector = PPEDetector()
    print(f"PPE Detector initialized with {len(detector.class_names)} classes")
    print(f"Classes: {detector.class_names}")