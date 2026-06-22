"""
Detection service for processing uploaded videos.
Supports video file upload, processing through the PPE detection pipeline,
and returning annotated results.
"""

import os
import sys
import uuid
import json
import time
import shutil
import threading
import subprocess
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import imageio_ffmpeg

# Add project root
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
)

from model.inference.detector import PPEDetector, DetectionResult, Detection
from video_processor.tracking.tracker import PPETracker, TrackedObject


# Upload directory
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "uploads",
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "processed",
)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@dataclass
class VideoJob:
    """Represents a video processing job."""

    job_id: str
    filename: str
    filepath: str
    status: str  # queued, processing, completed, failed
    stage: str  # queued, init_engine, open_video, process_frames, post_process
    progress: float  # 0.0 to 1.0
    total_frames: int
    processed_frames: int
    total_violations: int
    violations_by_type: Dict[str, int]
    person_count: int
    avg_inference_ms: float
    video_duration_sec: float
    output_path: Optional[str]
    created_at: float
    completed_at: Optional[float]
    error: Optional[str]



class DetectionService:
    """Service for processing uploaded video files through the PPE detection pipeline."""

    # Job retention controls (in seconds)
    JOB_TTL_SEC = 60 * 60  # 1 hour
    MAX_JOBS = 200

    # Guardrails to avoid jobs looking stuck forever
    ENGINE_INIT_TIMEOUT_SEC = 60
    VIDEO_OPEN_TIMEOUT_SEC = 30


    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.detector = None
        self.tracker = None
        self._init_error: Optional[Exception] = None

        self._jobs: Dict[str, VideoJob] = {}
        self._lock = threading.Lock()
        self._init_engine()

    def _init_engine(self):
        """Initialize the ML engine (lazy init on first use)."""
        self._init_error = None
        try:
            self.detector = PPEDetector(model_path=self.model_path)
            self.tracker = PPETracker()
            print("Detection engine initialized for video upload processing")
        except Exception as e:
            self.detector = None
            self.tracker = None
            self._init_error = e
            print(f"Warning: Detection engine init failed: {e}")
            print("Engine will be initialized on first job")

    def _ensure_engine(self):
        """Ensure the ML engine is initialized."""
        if self.detector is None:
            self._init_engine()

        if self.detector is None:
            if self._init_error is not None:
                raise RuntimeError(
                    f"Failed to initialize detection engine: {type(self._init_error).__name__}: {self._init_error}"
                )
            raise RuntimeError("Failed to initialize detection engine")

    def _cleanup_jobs_if_needed(self):
        """Best-effort cleanup of old jobs to prevent unbounded memory growth."""
        now = time.time()
        with self._lock:
            cutoff = now - self.JOB_TTL_SEC
            stale_ids = [
                jid
                for jid, j in self._jobs.items()
                if (j.completed_at or j.created_at) < cutoff
            ]
            for jid in stale_ids:
                self._jobs.pop(jid, None)

            if len(self._jobs) > self.MAX_JOBS:
                jobs_sorted = sorted(
                    self._jobs.values(),
                    key=lambda j: (j.completed_at or j.created_at),
                )
                for j in jobs_sorted[: len(self._jobs) - self.MAX_JOBS]:
                    self._jobs.pop(j.job_id, None)

    def submit_job(self, filepath: str, filename: str) -> str:
        """Submit a video file for processing."""
        job_id = str(uuid.uuid4())[:8]

        job = VideoJob(
            job_id=job_id,
            filename=filename,
            filepath=filepath,
            status="queued",
            stage="queued",
            progress=0.0,
            total_frames=0,
            processed_frames=0,
            total_violations=0,
            violations_by_type={},
            person_count=0,
            avg_inference_ms=0.0,
            video_duration_sec=0.0,
            output_path=None,
            created_at=time.time(),
            completed_at=None,
            error=None,
        )

        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(target=self._process_job, args=(job_id,), daemon=True)
        thread.start()

        return job_id

    def _get_job(self, job_id: str) -> Optional[VideoJob]:
        """Get job without copy (internal use)."""
        return self._jobs.get(job_id)

    def _process_job(self, job_id: str):
        """Process a video job in background."""
        job = self._get_job(job_id)
        if job is None:
            return

        output_path: Optional[str] = None

        try:
            with self._lock:
                job.status = "processing"
                job.stage = "init_engine"
                job.progress = max(job.progress, 0.02)

            # Ensure engine (fail-fast if weights missing)
            t0 = time.time()
            self._ensure_engine()
            if time.time() - t0 > self.ENGINE_INIT_TIMEOUT_SEC:
                raise TimeoutError(
                    f"Engine initialization exceeded {self.ENGINE_INIT_TIMEOUT_SEC}s"
                )

            with self._lock:
                job.stage = "open_video"
                job.progress = max(job.progress, 0.05)

            cap = cv2.VideoCapture(job.filepath)
            if not cap.isOpened():
                raise RuntimeError(f"Failed to open video: {job.filename}")

            t_open = time.time()
            # Best-effort: CAP_PROP_FRAME_COUNT can block on some backends
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if time.time() - t_open > self.VIDEO_OPEN_TIMEOUT_SEC:
                raise TimeoutError(
                    f"Video open/metadata exceeded {self.VIDEO_OPEN_TIMEOUT_SEC}s"
                )

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

            if width <= 0 or height <= 0:
                raise RuntimeError(
                    f"Invalid video dimensions for {job.filename}: {width}x{height}"
                )

            if fps <= 0:
                fps = 25.0

            video_duration = (
                total_frames / fps if (total_frames > 0 and fps > 0) else 0.0
            )

            with self._lock:
                job.total_frames = total_frames
                job.video_duration_sec = video_duration

            output_filename = f"{job_id}_{Path(job.filename).stem}_annotated.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            if not out.isOpened():
                raise RuntimeError(f"Failed to open VideoWriter for output: {output_path}")

            # Set output_path early so the download endpoint can serve partial results
            with self._lock:
                job.output_path = output_path

            # Speed up processing for uploads.
            # Higher value => fewer YOLO inferences (much faster for long videos).
            # NOTE: keep this conservative; we'll also throttle annotation work.
            skip_frames = 8

            with self._lock:
                job.stage = "process_frames"
                job.progress = max(job.progress, 0.1)

            frame_idx = 0

            processed_idx = 0
            total_violations = 0
            violations_by_type: Dict[str, int] = {}
            last_progress_update = 0.0
            last_annotated: Optional[np.ndarray] = None

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1

                current_progress = (frame_idx / total_frames) if total_frames > 0 else 0.0
                current_progress = min(current_progress, 1.0)
                if (
                    current_progress - last_progress_update >= 0.01
                    or frame_idx % 10 == 0
                ):
                    with self._lock:
                        job.progress = current_progress
                    last_progress_update = current_progress

                should_infer = frame_idx % (skip_frames + 1) == 0

                if not should_infer:
                    if last_annotated is not None:
                        out.write(last_annotated)
                    else:
                        out.write(frame)
                    continue

                try:
                    detection_result = self.detector.detect(frame)
                    detections = detection_result.detections
                    detection_result.detections = detections

                    if self.tracker:
                        tracked_objects = self.tracker.update(
                            detections, frame_idx, time.time()
                        )
                        for track in tracked_objects:
                            if track.track_id > 0:
                                for det in detections:
                                    iou = DetectionResult._calculate_iou(det.bbox, track.bbox)
                                    if iou > 0.5:
                                        det.track_id = track.track_id

                    violations = detection_result.get_ppe_violations()

                    for vtype, vlist in violations.items():
                        total_violations += len(vlist)
                        violations_by_type[vtype] = violations_by_type.get(vtype, 0) + len(vlist)

                    persons = [d for d in detections if d.class_name == "person"]
                    person_count = len(persons)

                    annotated = frame.copy()
                    annotated = self.detector.draw_detections(
                        annotated, detection_result, show_conf=False, show_track=True
                    )
                    annotated = self.detector.draw_violations(annotated, violations)
                    annotated = self.detector.draw_ppe_status(
                        annotated, violations, person_count
                    )

                    current_time = frame_idx / fps if fps > 0 else 0.0
                    minutes = int(current_time // 60)
                    seconds = int(current_time % 60)
                    cv2.putText(
                        annotated,
                        f"{minutes:02d}:{seconds:02d}",
                        (max(width - 120, 10), max(height - 20, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (200, 200, 200),
                        2,
                    )

                    last_annotated = annotated
                    out.write(annotated)
                    processed_idx += 1

                    with self._lock:
                        job.processed_frames = processed_idx
                        job.total_violations = total_violations
                        job.violations_by_type = dict(violations_by_type)
                        job.person_count = person_count
                        job.avg_inference_ms = (
                            (job.avg_inference_ms * 0.95)
                            + (detection_result.inference_time_ms * 0.05)
                        )

                except Exception as fe:
                    with self._lock:
                        job.error = (
                            f"Non-fatal frame processing error at frame {frame_idx}: {str(fe)}"
                        )

                    if last_annotated is not None:
                        out.write(last_annotated)
                    else:
                        out.write(frame)
                    continue

            cap.release()
            out.release()

            with self._lock:
                job.stage = "post_process"
                job.progress = max(job.progress, 0.9)

            fixed_output_path = None

            try:
                if output_path and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    fixed_output_path = os.path.join(
                        OUTPUT_DIR,
                        f"{job_id}_{Path(job.filename).stem}_annotated_fixed.mp4",
                    )

                    ffmpeg_bin = shutil.which("ffmpeg")
                    if not ffmpeg_bin:
                        try:
                            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
                        except Exception as ie:
                            print(f"Warning: could not resolve ffmpeg from imageio-ffmpeg: {ie}")
                    if not ffmpeg_bin or not os.path.exists(ffmpeg_bin):
                        raise FileNotFoundError(
                            "ffmpeg not found in PATH or imageio-ffmpeg; cannot post-process MP4"
                        )

                    cmd_reencode = [
                        ffmpeg_bin,
                        "-y",
                        "-i",
                        output_path,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "23",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        fixed_output_path,
                    ]
                    proc = subprocess.run(
                        cmd_reencode,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if (
                        proc.returncode != 0
                        or not os.path.exists(fixed_output_path)
                        or os.path.getsize(fixed_output_path) == 0
                    ):
                        fixed_output_path = None

            except Exception as fe:
                print(f"Warning: failed to post-process annotated video: {fe}")

            final_output = fixed_output_path or output_path

            with self._lock:
                job.status = "completed"
                job.progress = 1.0
                job.output_path = final_output
                job.completed_at = job.completed_at or time.time()

            print(f"Video processing completed: {job.filename} -> {output_filename}")

        except Exception as e:
            print(f"Error processing video {job_id}: {e}")
            import traceback

            traceback.print_exc()
            with self._lock:
                job.status = "failed"
                job.error = str(e)
                job.completed_at = job.completed_at or time.time()

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Get job status by ID."""
        self._cleanup_jobs_if_needed()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return VideoJob(**{k: v for k, v in asdict(job).items()})

    def get_all_jobs(self) -> List[VideoJob]:
        """Get all jobs."""
        self._cleanup_jobs_if_needed()
        with self._lock:
            return [
                VideoJob(**{k: v for k, v in asdict(j).items()})
                for j in self._jobs.values()
            ]


# Singleton instance
detection_service = DetectionService()

