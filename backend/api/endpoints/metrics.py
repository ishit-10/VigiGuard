"""
Metrics API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import Optional
import datetime

from backend.db.database import get_db
from backend.db.models import MetricSnapshot, ViolationRecord, Alert
from backend.schemas.schemas import MetricSnapshotResponse, MetricsSummary, MetricsListResponse

router = APIRouter()


@router.get("/summary", response_model=MetricsSummary)
async def get_metrics_summary(db: Session = Depends(get_db)):
    """Get comprehensive metrics summary."""
    now = datetime.datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total violations today
    total_violations_today = db.query(ViolationRecord).filter(
        ViolationRecord.timestamp >= today_start
    ).count()
    
    # Active alerts
    active_alerts = db.query(Alert).filter(
        Alert.status.in_(["active", "acknowledged"])
    ).count()
    
    # Current compliance from latest snapshot
    latest_snapshot = db.query(MetricSnapshot).order_by(desc(MetricSnapshot.timestamp)).first()
    compliance_rate = latest_snapshot.compliance_rate if latest_snapshot else 100.0
    
    # Total persons tracked
    total_persons = db.query(func.sum(MetricSnapshot.total_persons)).scalar() or 0
    
    # Violations by type today
    violations_by_type = {}
    for vtype in ['no_helmet', 'no_gloves', 'no_shoes', 'no_safety_suit']:
        count = db.query(ViolationRecord).filter(
            ViolationRecord.timestamp >= today_start,
            ViolationRecord.violation_type == vtype
        ).count()
        if count > 0:
            violations_by_type[vtype] = count
    
    # Hourly trend from today's snapshots
    snapshots_today = db.query(MetricSnapshot).filter(
        MetricSnapshot.timestamp >= today_start
    ).order_by(MetricSnapshot.timestamp).all()
    
    hourly_trend = []
    for snap in snapshots_today:
        hour_key = snap.window_start.strftime('%H:00')
        hourly_trend.append({
            'hour': hour_key,
            'violations': snap.total_violations,
            'workers': snap.peak_person_count,
            'compliance_rate': snap.compliance_rate,
        })
    
    # Alerts by severity
    alerts_by_severity = {}
    for severity in ['low', 'medium', 'high', 'critical']:
        count = db.query(Alert).filter(
            Alert.timestamp >= today_start,
            Alert.severity == severity,
            Alert.status == "active"
        ).count()
        if count > 0:
            alerts_by_severity[severity] = count
    
    return MetricsSummary(
        total_violations_today=total_violations_today,
        total_alerts_active=active_alerts,
        current_compliance_rate=compliance_rate,
        total_persons_tracked=total_persons,
        avg_response_time_minutes=0.0,  # TODO: compute from alert resolution times
        violations_by_type=violations_by_type,
        hourly_trend=hourly_trend,
        alerts_by_severity=alerts_by_severity,
    )


@router.get("/snapshots", response_model=MetricsListResponse)
async def get_metric_snapshots(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get metric snapshots."""
    snapshots = db.query(MetricSnapshot).order_by(
        desc(MetricSnapshot.timestamp)
    ).offset(skip).limit(limit).all()
    
    total = db.query(MetricSnapshot).count()
    
    return MetricsListResponse(
        total=total,
        snapshots=[MetricSnapshotResponse(
            id=s.id,
            timestamp=s.timestamp,
            window_start=s.window_start,
            window_end=s.window_end,
            total_detections=s.total_detections,
            total_persons=s.total_persons,
            avg_inference_ms=s.avg_inference_ms,
            avg_processing_ms=s.avg_processing_ms,
            peak_person_count=s.peak_person_count,
            total_violations=s.total_violations,
            no_helmet_count=s.no_helmet_count,
            no_gloves_count=s.no_gloves_count,
            no_shoes_count=s.no_shoes_count,
            no_safety_suit_count=s.no_safety_suit_count,
            compliance_rate=s.compliance_rate,
            alerts_generated=s.alerts_generated,
            alerts_resolved=s.alerts_resolved,
        ) for s in snapshots]
    )


@router.get("/compliance")
async def get_compliance_history(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get compliance rate history."""
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    
    snapshots = db.query(MetricSnapshot).filter(
        MetricSnapshot.timestamp >= since
    ).order_by(MetricSnapshot.timestamp).all()
    
    return {
        "compliance_history": [
            {
                "timestamp": s.timestamp.isoformat(),
                "compliance_rate": s.compliance_rate,
                "total_violations": s.total_violations,
                "total_persons": s.total_persons,
            }
            for s in snapshots
        ]
    }


@router.get("/violations-trend")
async def get_violations_trend(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """Get violations trend data."""
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    
    snapshots = db.query(MetricSnapshot).filter(
        MetricSnapshot.timestamp >= since
    ).order_by(MetricSnapshot.timestamp).all()
    
    return {
        "violations_trend": [
            {
                "timestamp": s.timestamp.isoformat(),
                "no_helmet": s.no_helmet_count,
                "no_gloves": s.no_gloves_count,
                "no_shoes": s.no_shoes_count,
                "no_safety_suit": s.no_safety_suit_count,
                "total": s.total_violations,
            }
            for s in snapshots
        ]
    }