"""
SQLAlchemy database models for DMRC PPE Tracking.
"""
import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from backend.db.database import Base


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ViolationType(str, enum.Enum):
    NO_HELMET = "no_helmet"
    NO_SAFETY_SUIT = "no_safety_suit"
    NO_SAFETY_SHOES = "no_safety_shoes"
    NO_GLOVES = "no_gloves"


class DetectionEvent(Base):
    """Record of a detection event from video processing."""
    __tablename__ = "detection_events"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    camera_id = Column(String(100), default="camera_01")
    frame_id = Column(Integer)
    person_count = Column(Integer, default=0)
    total_detections = Column(Integer, default=0)
    inference_time_ms = Column(Float, default=0.0)
    processing_time_ms = Column(Float, default=0.0)
    
    # Detections as JSON
    detections_json = Column(Text, nullable=True)  # JSON string of all detections
    violations_json = Column(Text, nullable=True)  # JSON string of violations
    
    # Relationships
    alerts = relationship("Alert", back_populates="detection_event")
    violations = relationship("ViolationRecord", back_populates="detection_event")


class ViolationRecord(Base):
    """Record of a specific PPE violation."""
    __tablename__ = "violation_records"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    detection_event_id = Column(Integer, ForeignKey("detection_events.id"), nullable=True)
    
    violation_type = Column(String(50), index=True)  # no_helmet, no_gloves, etc.
    severity = Column(String(20), default="medium")
    
    # Person info
    person_track_id = Column(Integer, nullable=True)
    person_bbox_x = Column(Float, nullable=True)
    person_bbox_y = Column(Float, nullable=True)
    person_bbox_w = Column(Float, nullable=True)
    person_bbox_h = Column(Float, nullable=True)
    
    # Camera/Zone
    camera_id = Column(String(100), default="camera_01")
    zone = Column(String(100), nullable=True)
    
    # Resolution
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    
    # Relationships
    detection_event = relationship("DetectionEvent", back_populates="violations")
    alert = relationship("Alert", back_populates="violation", uselist=False)


class Alert(Base):
    """Alert generated for PPE violations."""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    violation_type = Column(String(50), index=True)
    violation_id = Column(Integer, ForeignKey("violation_records.id"), nullable=True)
    detection_event_id = Column(Integer, ForeignKey("detection_events.id"), nullable=True)
    
    severity = Column(String(20), default="medium")
    status = Column(String(20), default="active")  # active, acknowledged, resolved
    message = Column(Text, nullable=True)
    
    # Notification tracking
    notified = Column(Boolean, default=False)
    notified_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Camera
    camera_id = Column(String(100), default="camera_01")
    
    # Relationships
    violation = relationship("ViolationRecord", back_populates="alert")
    detection_event = relationship("DetectionEvent", back_populates="alerts")


class MetricSnapshot(Base):
    """Aggregated metrics snapshots for dashboard."""
    __tablename__ = "metric_snapshots"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # Time window
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    window_duration_seconds = Column(Integer, default=300)
    
    # Detection metrics
    total_detections = Column(Integer, default=0)
    total_persons = Column(Integer, default=0)
    avg_inference_ms = Column(Float, default=0.0)
    avg_processing_ms = Column(Float, default=0.0)
    peak_person_count = Column(Integer, default=0)
    
    # Violation metrics
    total_violations = Column(Integer, default=0)
    no_helmet_count = Column(Integer, default=0)
    no_gloves_count = Column(Integer, default=0)
    no_shoes_count = Column(Integer, default=0)
    no_safety_suit_count = Column(Integer, default=0)
    
    # Compliance rate (0-100%)
    compliance_rate = Column(Float, default=100.0)
    
    # Alert metrics
    alerts_generated = Column(Integer, default=0)
    alerts_resolved = Column(Integer, default=0)
    
    # Camera
    camera_id = Column(String(100), default="camera_01")


class CameraConfig(Base):
    """Camera configuration."""
    __tablename__ = "camera_configs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(String(100), unique=True, index=True)
    name = Column(String(200))
    source = Column(String(500))  # camera index, RTSP URL, or file path
    location = Column(String(200), nullable=True)
    active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class SystemConfig(Base):
    """System configuration key-value store."""
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)