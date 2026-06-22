"""
System API endpoints for status, config, and pipeline management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
import datetime
import time
import os
import psutil

from backend.db.database import get_db
from backend.db.models import SystemConfig, MetricSnapshot, Alert, ViolationRecord, DetectionEvent
from backend.schemas.schemas import SystemStatusResponse

router = APIRouter()


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(db: Session = Depends(get_db)):
    """Get comprehensive system status."""
    now = datetime.datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get latest snapshot for metrics
    latest = db.query(MetricSnapshot).order_by(desc(MetricSnapshot.timestamp)).first()
    
    # Count violations today
    violations_today = db.query(ViolationRecord).filter(
        ViolationRecord.timestamp >= today_start
    ).count()
    
    # Active alerts
    active_alerts = db.query(Alert).filter(
        Alert.status == "active"
    ).count()
    
    # Memory usage
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    
    # Get app uptime
    from backend.core.app import app_state
    uptime = time.time() - app_state.get('start_time', time.time())
    
    return SystemStatusResponse(
        status="running" if app_state.get('running', False) else "idle",
        uptime_seconds=uptime,
        camera_active=app_state.get('running', False),
        detection_running=app_state.get('running', False),
        fps=latest.avg_processing_ms if latest else 0.0,
        total_violations_today=violations_today,
        alerts_active=active_alerts,
        compliance_rate=latest.compliance_rate if latest else 100.0,
        persons_current=latest.peak_person_count if latest else 0,
        total_persons_tracked=latest.total_persons if latest else 0,
        avg_inference_ms=latest.avg_inference_ms if latest else 0.0,
        memory_usage_mb=round(memory_mb, 2),
    )


@router.get("/config")
async def get_system_config(db: Session = Depends(get_db)):
    """Get system configuration."""
    configs = db.query(SystemConfig).all()
    return {c.key: c.value for c in configs}


@router.put("/config/{key}")
async def update_system_config(key: str, value: str, db: Session = Depends(get_db)):
    """Update a system configuration value."""
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    
    if config:
        config.value = value
        config.updated_at = datetime.datetime.utcnow()
    else:
        config = SystemConfig(key=key, value=value)
        db.add(config)
    
    db.commit()
    return {"key": key, "value": value}


@router.get("/info")
async def get_system_info():
    """Get system information."""
    return {
        "name": "DMRC PPE Tracking System",
        "version": "1.0.0",
        "python_version": __import__('sys').version,
        "platform": __import__('platform').platform(),
        "detection_model": "YOLOv8m",
        "ppe_classes": ["person", "helmet", "hands", "shoes", "safety_suit", "tools"],
        "api_prefix": "/api/v1",
        "documentation": "/docs",
    }