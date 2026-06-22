"""
Cameras API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import datetime

from backend.db.database import get_db
from backend.db.models import CameraConfig
from backend.schemas.schemas import CameraResponse, CameraCreateRequest, CameraUpdateRequest

router = APIRouter()


@router.get("/", response_model=List[CameraResponse])
async def get_cameras(db: Session = Depends(get_db)):
    """Get all configured cameras."""
    cameras = db.query(CameraConfig).all()
    
    return [CameraResponse(
        id=c.id,
        camera_id=c.camera_id,
        name=c.name,
        source=c.source,
        location=c.location,
        active=c.active,
        created_at=c.created_at,
        updated_at=c.updated_at,
    ) for c in cameras]


@router.get("/{camera_id_str}", response_model=CameraResponse)
async def get_camera(camera_id_str: str, db: Session = Depends(get_db)):
    """Get a specific camera by camera_id."""
    camera = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id_str
    ).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraResponse(
        id=camera.id,
        camera_id=camera.camera_id,
        name=camera.name,
        source=camera.source,
        location=camera.location,
        active=camera.active,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


@router.post("/", response_model=CameraResponse, status_code=201)
async def create_camera(camera: CameraCreateRequest, db: Session = Depends(get_db)):
    """Register a new camera."""
    existing = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera.camera_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Camera ID already exists")
    
    db_camera = CameraConfig(
        camera_id=camera.camera_id,
        name=camera.name,
        source=camera.source,
        location=camera.location,
        active=True,
    )
    db.add(db_camera)
    db.commit()
    db.refresh(db_camera)
    
    return CameraResponse(
        id=db_camera.id,
        camera_id=db_camera.camera_id,
        name=db_camera.name,
        source=db_camera.source,
        location=db_camera.location,
        active=db_camera.active,
        created_at=db_camera.created_at,
        updated_at=db_camera.updated_at,
    )


@router.put("/{camera_id_str}", response_model=CameraResponse)
async def update_camera(
    camera_id_str: str,
    update: CameraUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update camera configuration."""
    camera = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id_str
    ).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    if update.name is not None:
        camera.name = update.name
    if update.source is not None:
        camera.source = update.source
    if update.location is not None:
        camera.location = update.location
    if update.active is not None:
        camera.active = update.active
    
    camera.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(camera)
    
    return CameraResponse(
        id=camera.id,
        camera_id=camera.camera_id,
        name=camera.name,
        source=camera.source,
        location=camera.location,
        active=camera.active,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


@router.delete("/{camera_id_str}")
async def delete_camera(camera_id_str: str, db: Session = Depends(get_db)):
    """Remove a camera configuration."""
    camera = db.query(CameraConfig).filter(
        CameraConfig.camera_id == camera_id_str
    ).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    db.delete(camera)
    db.commit()
    
    return {"status": "deleted", "camera_id": camera_id_str}