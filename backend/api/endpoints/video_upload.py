"""
API endpoints for uploading and processing video files for PPE detection.
"""
import asyncio
import os
import sys
import uuid
import json
import time
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Optional

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.services.detection.detection_service import (
    detection_service, UPLOAD_DIR, OUTPUT_DIR
)

router = APIRouter()

# Allowed video file extensions
ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video file for PPE detection processing.
    
    The video is saved to the uploads directory and a processing job is created.
    Returns a job ID that can be used to track progress.
    """
    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save uploaded file by streaming in chunks to avoid loading entire file into memory
    try:
        total_bytes = 0
        CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks

        # Lightweight instrumentation so we can confirm the request is making progress.
        # (Useful when diagnosing client-visible "uploading stuck".)
        last_log_time = time.time()
        last_log_bytes = 0
        log_every_bytes = 64 * 1024 * 1024  # log every 64MB
        log_every_seconds = 10

        with open(filepath, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                total_bytes += len(chunk)

                if total_bytes > MAX_FILE_SIZE:
                    f.close()
                    os.remove(filepath)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
                    )

                # Blocking disk write is kept as-is for minimal risk,
                # but we now log so stalls are visible.
                f.write(chunk)

                now = time.time()
                should_log = (
                    (total_bytes - last_log_bytes) >= log_every_bytes
                    or (now - last_log_time) >= log_every_seconds
                )
                if should_log:
                    received_mb = round(total_bytes / (1024 * 1024), 2)
                    delta_mb = round((total_bytes - last_log_bytes) / (1024 * 1024), 2)
                    elapsed = round(now - last_log_time, 2)
                    print(
                        f"[video_upload] saving {file.filename} -> {unique_filename}: "
                        f"received={received_mb}MB (delta={delta_mb}MB/{elapsed}s)"  # noqa: T201
                    )
                    last_log_time = now
                    last_log_bytes = total_bytes

    except HTTPException:
        raise
    except Exception as e:
        # Clean up partial file on error
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    except asyncio.CancelledError:
        # Client disconnected / request cancelled mid-upload.
        # Best-effort cleanup of partial file.
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        raise

    
    # Submit processing job
    try:
        job_id = detection_service.submit_job(filepath, file.filename)
    except Exception as e:
        # Clean up file if job submission fails
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")
    
    return {
        "job_id": job_id,
        "filename": file.filename,
        "status": "queued",
        "message": "Video uploaded and queued for processing", 
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status and results of a video processing job.
    """
    job = detection_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job.job_id,
        "filename": job.filename,
        "status": job.status,
        "stage": getattr(job, 'stage', None),
        "progress": job.progress,

        "total_frames": job.total_frames,
        "processed_frames": job.processed_frames,
        "total_violations": job.total_violations,
        "violations_by_type": job.violations_by_type,
        "person_count": job.person_count,
        "avg_inference_ms": round(job.avg_inference_ms or 0.0, 2),
        "video_duration_sec": round(job.video_duration_sec or 0.0, 1),
        # Frontend (Vite) uses API_BASE = '/api/v1' and Vite proxy for '/api'.
        # Return a URL that matches that contract.
        "output_path": f"/api/v1/video-upload/download/{job.job_id}" if job.status == "completed" else None,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error": job.error,
    }


@router.get("/jobs")
async def list_jobs():
    """
    List all video processing jobs.
    """
    jobs = detection_service.get_all_jobs()
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "filename": j.filename,
                "status": j.status,
                "progress": j.progress,
                "total_violations": j.total_violations,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in reversed(jobs)
        ],
        "total": len(jobs),
    }


@router.get("/download/{job_id}")
async def download_processed_video(job_id: str, request: Request):
    """Serve the processed (annotated) video with HTTP Range support.

    This enables inline <video> playback and seeking in browsers.
    """

    job = detection_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Allow streaming while the job is still processing.
    # The writer updates the MP4 file incrementally; we serve whatever bytes exist.
    if not job.output_path or not os.path.exists(job.output_path):
        # If output path isn’t set yet (writer not initialized), fall back to 404.
        # Frontend will try again on next poll.
        raise HTTPException(status_code=404, detail="Processed video file not found")

    file_path = job.output_path

    # Total size (may grow while processing)
    file_size = os.path.getsize(file_path)
    if file_size <= 0:
        raise HTTPException(status_code=404, detail="Processed video file not available yet")


    # Determine requested byte range
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path=file_path,
            filename=f"annotated_{job.filename}",
            media_type="video/mp4",
        )

    # Example: "bytes=0-1023"
    try:
        unit, range_spec = range_header.split("=", 1)
        if unit.strip().lower() != "bytes":
            raise ValueError("Unsupported range unit")

        start_str, end_str = range_spec.strip().split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1

        # Clamp/validate (file can be growing while we serve it)
        if start < 0:
            start = 0
        if end < 0:
            end = 0
        if end >= file_size:
            end = file_size - 1
        if start > end:
            start, end = end, start

        chunk_size = (end - start) + 1

    except Exception:
        # If range is malformed, fall back to full file
        return FileResponse(
            path=file_path,
            filename=f"annotated_{job.filename}",
            media_type="video/mp4",
        )

    def iter_file_chunks(path: str, offset: int, length: int, chunk: int = 1024 * 1024):
        with open(path, "rb") as f:
            f.seek(offset)
            remaining = length
            while remaining > 0:
                to_read = min(chunk, remaining)
                data = f.read(to_read)
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
    }

    # StreamingResponse will automatically set the status + media-type.
    # Provide headers needed for HTML5 video seeking.
    return StreamingResponse(
        iter_file_chunks(file_path, start, chunk_size),
        status_code=206,
        media_type="video/mp4",
        headers=headers,
    )

