"""
Metrics tracking and aggregation service for PPE compliance monitoring.
"""
import os
import sys
import yaml
import json
import datetime
import time
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from threading import Lock
from dataclasses import dataclass, field

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                           "config", "backend", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


class MetricsService:
    """
    Metrics tracking and aggregation service.
    Computes compliance rates, violation trends, and performance metrics.
    """
    
    def __init__(self, db_session=None):
        """
        Initialize metrics service.
        
        Args:
            db_session: Optional SQLAlchemy database session
        """
        self.db = db_session
        self.aggregation_interval = config['metrics']['aggregation_interval']
        self.retention_days = config['metrics']['retention_days']
        
        # In-memory metric buffers
        self._violation_buffer = deque(maxlen=10000)
        self._detection_buffer = deque(maxlen=5000)
        self._alerts_buffer = deque(maxlen=1000)
        
        # Time-series data for trending
        self._hourly_violations = defaultdict(int)
        self._hourly_persons = defaultdict(int)
        self._hourly_compliance = defaultdict(list)
        
        # Current session metrics
        self._session_start = time.time()
        self._current_metrics = {
            'total_frames': 0,
            'total_persons': 0,
            'total_violations': 0,
            'total_alerts': 0,
            'peak_concurrent_workers': 0,
            'avg_inference_ms': 0.0,
            'avg_processing_ms': 0.0,
        }
        
        self._lock = Lock()
        self._last_aggregation = time.time()
    
    def record_detection(self, person_count: int, total_detections: int,
                         inference_ms: float, processing_ms: float,
                         timestamp: Optional[float] = None):
        """Record a detection event."""
        ts = timestamp or time.time()
        
        with self._lock:
            self._detection_buffer.append({
                'timestamp': ts,
                'person_count': person_count,
                'total_detections': total_detections,
                'inference_ms': inference_ms,
                'processing_ms': processing_ms,
            })
            
            # Update current session metrics
            m = self._current_metrics
            m['total_frames'] += 1
            m['total_persons'] += person_count
            m['peak_concurrent_workers'] = max(m['peak_concurrent_workers'], person_count)
            m['avg_inference_ms'] = m['avg_inference_ms'] * 0.95 + inference_ms * 0.05
            m['avg_processing_ms'] = m['avg_processing_ms'] * 0.95 + processing_ms * 0.05
            
            # Hourly tracking
            hour_key = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:00')
            self._hourly_persons[hour_key] = max(self._hourly_persons[hour_key], person_count)
        
        # Check if aggregation needed
        self._check_aggregation()
    
    def record_violation(self, violation_type: str, severity: str,
                         person_track_id: Optional[int] = None,
                         timestamp: Optional[float] = None):
        """Record a PPE violation."""
        ts = timestamp or time.time()
        
        with self._lock:
            self._violation_buffer.append({
                'timestamp': ts,
                'violation_type': violation_type,
                'severity': severity,
                'person_track_id': person_track_id,
            })
            
            m = self._current_metrics
            m['total_violations'] += 1
            
            # Hourly tracking
            hour_key = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:00')
            self._hourly_violations[hour_key] += 1
        
        self._check_aggregation()
    
    def record_alert(self, alert_type: str, severity: str):
        """Record an alert generation."""
        with self._lock:
            self._alerts_buffer.append({
                'timestamp': time.time(),
                'alert_type': alert_type,
                'severity': severity,
            })
            self._current_metrics['total_alerts'] += 1
    
    def _check_aggregation(self):
        """Check if it's time to aggregate and persist metrics."""
        current_time = time.time()
        if current_time - self._last_aggregation >= self.aggregation_interval:
            self._aggregate_and_persist()
            self._last_aggregation = current_time
    
    def _aggregate_and_persist(self):
        """Aggregate current buffer and persist to database."""
        if self.db is None:
            return
        
        try:
            from backend.db.models import MetricSnapshot
            
            now = datetime.datetime.utcnow()
            window_start = now - datetime.timedelta(seconds=self.aggregation_interval)
            
            # Calculate metrics from buffers
            violations_since = [v for v in self._violation_buffer 
                              if v['timestamp'] >= window_start.timestamp()]
            detections_since = [d for d in self._detection_buffer 
                              if d['timestamp'] >= window_start.timestamp()]
            
            total_violations = len(violations_since)
            no_helmet = sum(1 for v in violations_since if v['violation_type'] == 'no_helmet')
            no_gloves = sum(1 for v in violations_since if v['violation_type'] == 'no_gloves')
            no_shoes = sum(1 for v in violations_since if v['violation_type'] == 'no_shoes')
            no_suit = sum(1 for v in violations_since if v['violation_type'] == 'no_safety_suit')
            
            total_persons = sum(d['person_count'] for d in detections_since)
            avg_inference = np.mean([d['inference_ms'] for d in detections_since]) if detections_since else 0
            avg_processing = np.mean([d['processing_ms'] for d in detections_since]) if detections_since else 0
            peak_persons = max([d['person_count'] for d in detections_since]) if detections_since else 0
            
            # Compliance rate: persons without any violation / total persons
            total_opportunities = total_persons  # each person is an opportunity for compliance
            compliance_rate = 100.0
            if total_opportunities > 0:
                violation_opportunities = total_violations * 4  # 4 PPE types checked per person
                compliant = max(0, total_opportunities * 4 - violation_opportunities)
                total_checks = total_opportunities * 4
                compliance_rate = (compliant / total_checks * 100) if total_checks > 0 else 100.0
                compliance_rate = min(100.0, max(0.0, compliance_rate))
            
            # Create snapshot
            snapshot = MetricSnapshot(
                window_start=window_start,
                window_end=now,
                window_duration_seconds=self.aggregation_interval,
                total_detections=len(detections_since),
                total_persons=total_persons,
                avg_inference_ms=float(avg_inference),
                avg_processing_ms=float(avg_processing),
                peak_person_count=peak_persons,
                total_violations=total_violations,
                no_helmet_count=no_helmet,
                no_gloves_count=no_gloves,
                no_shoes_count=no_shoes,
                no_safety_suit_count=no_suit,
                compliance_rate=float(compliance_rate),
                alerts_generated=len(self._alerts_buffer),
                alerts_resolved=0,
            )
            
            self.db.add(snapshot)
            self.db.commit()
            
        except Exception as e:
            print(f"Error aggregating metrics: {e}")
            self.db.rollback()
    
    def get_current_compliance_rate(self) -> float:
        """Get current compliance rate."""
        with self._lock:
            violations = len(self._violation_buffer)
            if violations == 0:
                return 100.0
            
            total_persons = self._current_metrics['total_persons']
            if total_persons == 0:
                return 100.0
            
            total_checks = total_persons * 4  # 4 PPE items per person
            non_compliant_checks = violations
            compliant_checks = max(0, total_checks - non_compliant_checks)
            
            return min(100.0, (compliant_checks / total_checks * 100) if total_checks > 0 else 100.0)
    
    def get_summary(self) -> Dict:
        """Get metrics summary for dashboard."""
        with self._lock:
            m = self._current_metrics
            
            # Violations by type
            violations_by_type = defaultdict(int)
            for v in self._violation_buffer:
                violations_by_type[v['violation_type']] += 1
            
            # Hourly trend (last 24 hours)
            hourly_trend = []
            now = datetime.datetime.utcnow()
            for i in range(24):
                hour = now - datetime.timedelta(hours=i)
                hour_key = hour.strftime('%Y-%m-%d %H:00')
                hourly_trend.append({
                    'hour': hour.strftime('%H:00'),
                    'violations': self._hourly_violations.get(hour_key, 0),
                    'workers': self._hourly_persons.get(hour_key, 0),
                })
            
            # Alerts by severity
            alerts_by_severity = defaultdict(int)
            for a in self._alerts_buffer:
                alerts_by_severity[a['severity']] += 1
            
            # Calculate active alerts
            active_alerts = sum(1 for a in self._alerts_buffer)
            
            return {
                'total_violations_today': m['total_violations'],
                'total_alerts_active': active_alerts,
                'current_compliance_rate': self.get_current_compliance_rate(),
                'total_persons_tracked': m['total_persons'],
                'avg_response_time_minutes': 0.0,  # TODO: calculate from alert resolution times
                'violations_by_type': dict(violations_by_type),
                'hourly_trend': list(reversed(hourly_trend)),
                'alerts_by_severity': dict(alerts_by_severity),
                'peak_concurrent_workers': m['peak_concurrent_workers'],
                'avg_inference_ms': m['avg_inference_ms'],
            }
    
    def get_recent_snapshots(self, limit: int = 100) -> List:
        """Get recent metric snapshots from database."""
        if self.db is None:
            return []
        
        try:
            from backend.db.models import MetricSnapshot
            snapshots = self.db.query(MetricSnapshot).order_by(
                MetricSnapshot.timestamp.desc()
            ).limit(limit).all()
            return snapshots
        except Exception as e:
            print(f"Error fetching snapshots: {e}")
            return []
    
    def set_database(self, db_session):
        """Set database session."""
        self.db = db_session
    
    def reset_session(self):
        """Reset current session metrics."""
        with self._lock:
            self._violation_buffer.clear()
            self._detection_buffer.clear()
            self._alerts_buffer.clear()
            self._current_metrics = {
                'total_frames': 0,
                'total_persons': 0,
                'total_violations': 0,
                'total_alerts': 0,
                'peak_concurrent_workers': 0,
                'avg_inference_ms': 0.0,
                'avg_processing_ms': 0.0,
            }
            self._session_start = time.time()