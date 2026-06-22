"""
Pydantic schemas for API request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ===== Alert Schemas =====

class AlertSeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertStatusEnum(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"

class AlertResponse(BaseModel):
    id: int
    timestamp: datetime
    violation_type: str
    severity: str
    status: str
    message: Optional[str] = None
    camera_id: str
    notified: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class AlertListResponse(BaseModel):
    total: int
    alerts: List[AlertResponse]

class AlertUpdateRequest(BaseModel):
    status: AlertStatusEnum
    acknowledged_by: Optional[str] = None


# ===== Violation Schemas =====

class ViolationResponse(BaseModel):
    id: int
    timestamp: datetime
    violation_type: str
    severity: str
    person_track_id: Optional[int] = None
    camera_id: str
    resolved: bool = False
    
    class Config:
        from_attributes = True

class ViolationListResponse(BaseModel):
    total: int
    violations: List[ViolationResponse]


# ===== Detection Schemas =====

class DetectionItem(BaseModel):
    class_name: str
    confidence: float
    bbox: List[int]  # x1, y1, x2, y2
    track_id: Optional[int] = None

class DetectionEventResponse(BaseModel):
    id: int
    timestamp: datetime
    camera_id: str
    frame_id: Optional[int] = None
    person_count: int
    total_detections: int
    inference_time_ms: float
    detections: Optional[List[DetectionItem]] = None
    violations: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class DetectionEventListResponse(BaseModel):
    total: int
    events: List[DetectionEventResponse]


# ===== Metrics Schemas =====

class MetricSnapshotResponse(BaseModel):
    id: int
    timestamp: datetime
    window_start: datetime
    window_end: datetime
    
    total_detections: int
    total_persons: int
    avg_inference_ms: float
    avg_processing_ms: float
    peak_person_count: int
    
    total_violations: int
    no_helmet_count: int = 0
    no_gloves_count: int = 0
    no_shoes_count: int = 0
    no_safety_suit_count: int = 0
    
    compliance_rate: float
    alerts_generated: int
    alerts_resolved: int
    
    class Config:
        from_attributes = True

class MetricsSummary(BaseModel):
    total_violations_today: int
    total_alerts_active: int
    current_compliance_rate: float
    total_persons_tracked: int
    avg_response_time_minutes: float
    violations_by_type: Dict[str, int]
    hourly_trend: List[Dict[str, Any]]
    alerts_by_severity: Dict[str, int]

class MetricsListResponse(BaseModel):
    total: int
    snapshots: List[MetricSnapshotResponse]


# ===== Camera Schemas =====

class CameraCreateRequest(BaseModel):
    camera_id: str
    name: str
    source: str
    location: Optional[str] = None

class CameraUpdateRequest(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None
    location: Optional[str] = None
    active: Optional[bool] = None

class CameraResponse(BaseModel):
    id: int
    camera_id: str
    name: str
    source: str
    location: Optional[str] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ===== System Schemas =====

class SystemStatusResponse(BaseModel):
    status: str  # running, stopped, error
    uptime_seconds: float
    camera_active: bool
    detection_running: bool
    fps: float
    total_violations_today: int
    alerts_active: int
    compliance_rate: float
    persons_current: int
    total_persons_tracked: int
    avg_inference_ms: float
    memory_usage_mb: float

class DetectionResultResponse(BaseModel):
    detections: List[Dict[str, Any]]
    violations: Dict[str, List[Dict[str, Any]]]
    person_count: int
    frame_id: int
    inference_time_ms: float
    fps: float