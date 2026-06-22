"""
Alerts API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
import datetime

from backend.db.database import get_db
from backend.db.models import Alert
from backend.schemas.schemas import AlertResponse, AlertListResponse, AlertUpdateRequest, AlertStatusEnum

router = APIRouter()


@router.get("/", response_model=AlertListResponse)
async def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get alerts with optional filters."""
    query = db.query(Alert)
    
    if status:
        query = query.filter(Alert.status == status)
    if severity:
        query = query.filter(Alert.severity == severity)
    
    total = query.count()
    alerts = query.order_by(desc(Alert.timestamp)).offset(skip).limit(limit).all()
    
    return AlertListResponse(
        total=total,
        alerts=[AlertResponse(
            id=a.id,
            timestamp=a.timestamp,
            violation_type=a.violation_type,
            severity=a.severity,
            status=a.status,
            message=a.message,
            camera_id=a.camera_id,
            notified=a.notified,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
            resolved_at=a.resolved_at,
        ) for a in alerts]
    )


@router.get("/active", response_model=AlertListResponse)
async def get_active_alerts(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get active (unresolved) alerts."""
    alerts = db.query(Alert).filter(
        Alert.status.in_(["active", "acknowledged"])
    ).order_by(desc(Alert.timestamp)).limit(limit).all()
    
    return AlertListResponse(
        total=len(alerts),
        alerts=[AlertResponse(
            id=a.id,
            timestamp=a.timestamp,
            violation_type=a.violation_type,
            severity=a.severity,
            status=a.status,
            message=a.message,
            camera_id=a.camera_id,
            notified=a.notified,
            acknowledged_at=a.acknowledged_at,
            acknowledged_by=a.acknowledged_by,
            resolved_at=a.resolved_at,
        ) for a in alerts]
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Get a specific alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=alert.id,
        timestamp=alert.timestamp,
        violation_type=alert.violation_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        camera_id=alert.camera_id,
        notified=alert.notified,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
    )


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    update: AlertUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update alert status (acknowledge/resolve)."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = update.status.value
    
    if update.status == AlertStatusEnum.ACKNOWLEDGED:
        alert.acknowledged_at = datetime.datetime.utcnow()
        alert.acknowledged_by = update.acknowledged_by or "operator"
    elif update.status == AlertStatusEnum.RESOLVED:
        alert.resolved_at = datetime.datetime.utcnow()
    
    db.commit()
    db.refresh(alert)
    
    return AlertResponse(
        id=alert.id,
        timestamp=alert.timestamp,
        violation_type=alert.violation_type,
        severity=alert.severity,
        status=alert.status,
        message=alert.message,
        camera_id=alert.camera_id,
        notified=alert.notified,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        resolved_at=alert.resolved_at,
    )


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    acknowledged_by: str = "operator",
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.datetime.utcnow()
    alert.acknowledged_by = acknowledged_by
    db.commit()
    
    return {"status": "acknowledged", "alert_id": alert_id}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Resolve an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = "resolved"
    alert.resolved_at = datetime.datetime.utcnow()
    db.commit()
    
    return {"status": "resolved", "alert_id": alert_id}