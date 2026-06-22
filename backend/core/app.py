"""
FastAPI application for DMRC PPE Tracking API.
"""
import os
import sys
import yaml
import time
import json
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import List, Optional
import threading

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "backend", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

# Global state
app_state = {
    'start_time': time.time(),
    'pipeline': None,
    'alert_service': None,
    'metrics_service': None,
    'db_session': None,
    'pipeline_thread': None,
    'running': False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    from backend.db.database import init_db, SessionLocal
    init_db()
    
    # Create DB session
    app_state['db_session'] = SessionLocal()
    
    # Initialize services
    from backend.notifications.alert_service import AlertService
    from backend.services.metrics.metrics_service import MetricsService
    
    app_state['alert_service'] = AlertService(db_session=app_state['db_session'])
    app_state['metrics_service'] = MetricsService(db_session=app_state['db_session'])
    
    print(f"API server started - {config['app']['name']} v{config['app']['version']}")
    
    yield
    
    # Shutdown
    if app_state['pipeline']:
        app_state['pipeline'].stop()
    
    if app_state['db_session']:
        app_state['db_session'].close()
    
    print("API server shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=config['app']['name'],
    version=config['app']['version'],
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config['cors']['origins'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== Dependency =====
def get_db():
    """Get database session."""
    from backend.db.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_alert_service(db: Session = Depends(get_db)):
    """Get alert service with DB session."""
    from backend.notifications.alert_service import AlertService
    return AlertService(db_session=db)


def get_metrics_service(db: Session = Depends(get_db)):
    """Get metrics service with DB session."""
    from backend.services.metrics.metrics_service import MetricsService
    return MetricsService(db_session=db)


# ===== Import Routers =====
from backend.api.endpoints import detection, alerts, violations, metrics, cameras, system, ws, video_upload

app.include_router(detection.router, prefix="/api/v1/detection", tags=["Detection"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(violations.router, prefix="/api/v1/violations", tags=["Violations"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])
app.include_router(cameras.router, prefix="/api/v1/cameras", tags=["Cameras"])
app.include_router(system.router, prefix="/api/v1/system", tags=["System"])
app.include_router(ws.router, prefix="/api/v1/ws", tags=["WebSocket"])
app.include_router(video_upload.router, prefix="/api/v1/video-upload", tags=["Video Upload"])


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": config['app']['name'],
        "version": config['app']['version'],
        "status": "running",
        "uptime_seconds": time.time() - app_state['start_time'],
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
    }


def run_pipeline(source: str = "0"):
    """Run the detection pipeline in background."""
    from video_processor.detection.pipeline import DetectionPipeline
    
    pipeline = DetectionPipeline(source=source)
    if pipeline.initialize():
        pipeline.register_callback(on_pipeline_frame)
        app_state['pipeline'] = pipeline
        app_state['running'] = True
        pipeline.run()
    app_state['running'] = False


def on_pipeline_frame(pipeline_frame):
    """Callback for processed pipeline frames."""
    try:
        # Record metrics
        if app_state['metrics_service']:
            app_state['metrics_service'].record_detection(
                person_count=pipeline_frame.person_count,
                total_detections=len(pipeline_frame.detections),
                inference_ms=pipeline_frame.inference_time_ms,
                processing_ms=pipeline_frame.total_process_time_ms,
            )
        
        # Check violations and generate alerts
        if app_state['alert_service'] and pipeline_frame.violations:
            alerts = app_state['alert_service'].check_violations(
                violations=pipeline_frame.violations,
                frame_id=pipeline_frame.frame_id,
                timestamp=pipeline_frame.timestamp,
                detections=pipeline_frame.detections,
            )
            
            # Record violation metrics
            for alert in alerts:
                if app_state['metrics_service']:
                    app_state['metrics_service'].record_violation(
                        violation_type=alert.violation_type,
                        severity=alert.severity,
                        person_track_id=alert.person_track_id,
                    )
                    app_state['metrics_service'].record_alert(
                        alert_type=alert.violation_type,
                        severity=alert.severity,
                    )
    except Exception as e:
        print(f"Pipeline callback error: {e}")


@app.post("/api/v1/system/start-pipeline")
async def start_pipeline(source: str = "0"):
    """Start the detection pipeline."""
    if app_state['running']:
        return {"status": "already_running", "message": "Pipeline is already running"}
    
    thread = threading.Thread(target=run_pipeline, args=(source,), daemon=True)
    thread.start()
    app_state['pipeline_thread'] = thread
    
    return {"status": "started", "message": f"Pipeline started with source: {source}"}


@app.post("/api/v1/system/stop-pipeline")
async def stop_pipeline():
    """Stop the detection pipeline."""
    if app_state['pipeline']:
        app_state['pipeline'].stop()
        app_state['running'] = False
        return {"status": "stopped", "message": "Pipeline stopped"}
    return {"status": "not_running", "message": "Pipeline is not running"}