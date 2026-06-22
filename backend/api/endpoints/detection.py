"""
Detection API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
import json

from backend.db.database import get_db
from backend.db.models import DetectionEvent
from backend.schemas.schemas import DetectionEventResponse, DetectionEventListResponse, DetectionItem

router = APIRouter()


@router.get("/events", response_model=DetectionEventListResponse)
async def get_detection_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get recent detection events."""
    events = db.query(DetectionEvent).order_by(
        desc(DetectionEvent.timestamp)
    ).offset(skip).limit(limit).all()
    
    total = db.query(DetectionEvent).count()
    
    return DetectionEventListResponse(
        total=total,
        events=[DetectionEventResponse(
            id=e.id,
            timestamp=e.timestamp,
            camera_id=e.camera_id,
            frame_id=e.frame_id,
            person_count=e.person_count,
            total_detections=e.total_detections,
            inference_time_ms=e.inference_time_ms,
            detections=json.loads(e.detections_json) if e.detections_json else None,
            violations=json.loads(e.violations_json) if e.violations_json else None,
        ) for e in events]
    )


@router.get("/events/{event_id}", response_model=DetectionEventResponse)
async def get_detection_event(event_id: int, db: Session = Depends(get_db)):
    """Get a specific detection event."""
    event = db.query(DetectionEvent).filter(DetectionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Detection event not found")
    
    return DetectionEventResponse(
        id=event.id,
        timestamp=event.timestamp,
        camera_id=event.camera_id,
        frame_id=event.frame_id,
        person_count=event.person_count,
        total_detections=event.total_detections,
        inference_time_ms=event.inference_time_ms,
        detections=json.loads(event.detections_json) if event.detections_json else None,
        violations=json.loads(event.violations_json) if event.violations_json else None,
    )


@router.get("/latest")
async def get_latest_detection(db: Session = Depends(get_db)):
    """Get the latest detection event."""
    event = db.query(DetectionEvent).order_by(desc(DetectionEvent.timestamp)).first()
    if not event:
        return {"status": "no_data", "message": "No detection events recorded yet"}
    
    return {
        "timestamp": event.timestamp.isoformat(),
        "person_count": event.person_count,
        "total_detections": event.total_detections,
        "inference_time_ms": event.inference_time_ms,
        "detections": json.loads(event.detections_json) if event.detections_json else [],
        "violations": json.loads(event.violations_json) if event.violations_json else {},
    }