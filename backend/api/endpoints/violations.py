"""
Violations API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
import datetime

from backend.db.database import get_db
from backend.db.models import ViolationRecord
from backend.schemas.schemas import ViolationResponse, ViolationListResponse

router = APIRouter()


@router.get("/", response_model=ViolationListResponse)
async def get_violations(
    violation_type: Optional[str] = Query(None, description="Filter by violation type"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get violations with optional filters."""
    query = db.query(ViolationRecord)
    
    if violation_type:
        query = query.filter(ViolationRecord.violation_type == violation_type)
    if resolved is not None:
        query = query.filter(ViolationRecord.resolved == resolved)
    
    total = query.count()
    violations = query.order_by(desc(ViolationRecord.timestamp)).offset(skip).limit(limit).all()
    
    return ViolationListResponse(
        total=total,
        violations=[ViolationResponse(
            id=v.id,
            timestamp=v.timestamp,
            violation_type=v.violation_type,
            severity=v.severity,
            person_track_id=v.person_track_id,
            camera_id=v.camera_id,
            resolved=v.resolved,
        ) for v in violations]
    )


@router.get("/summary")
async def get_violations_summary(db: Session = Depends(get_db)):
    """Get violations summary statistics."""
    now = datetime.datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total today
    total_today = db.query(ViolationRecord).filter(
        ViolationRecord.timestamp >= today_start
    ).count()
    
    # By type today
    types_today = {}
    for vtype in ['no_helmet', 'no_gloves', 'no_shoes', 'no_safety_suit']:
        count = db.query(ViolationRecord).filter(
            ViolationRecord.timestamp >= today_start,
            ViolationRecord.violation_type == vtype
        ).count()
        if count > 0:
            types_today[vtype] = count
    
    # Unresolved
    unresolved = db.query(ViolationRecord).filter(
        ViolationRecord.resolved == False
    ).count()
    
    return {
        "total_today": total_today,
        "unresolved": unresolved,
        "by_type_today": types_today,
        "date": today_start.isoformat(),
    }


@router.get("/{violation_id}", response_model=ViolationResponse)
async def get_violation(violation_id: int, db: Session = Depends(get_db)):
    """Get a specific violation."""
    violation = db.query(ViolationRecord).filter(ViolationRecord.id == violation_id).first()
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")
    
    return ViolationResponse(
        id=violation.id,
        timestamp=violation.timestamp,
        violation_type=violation.violation_type,
        severity=violation.severity,
        person_track_id=violation.person_track_id,
        camera_id=violation.camera_id,
        resolved=violation.resolved,
    )


@router.post("/{violation_id}/resolve")
async def resolve_violation(violation_id: int, resolved_by: str = "operator", db: Session = Depends(get_db)):
    """Mark a violation as resolved."""
    violation = db.query(ViolationRecord).filter(ViolationRecord.id == violation_id).first()
    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")
    
    violation.resolved = True
    violation.resolved_at = datetime.datetime.utcnow()
    violation.resolved_by = resolved_by
    db.commit()
    
    return {"status": "resolved", "violation_id": violation_id}