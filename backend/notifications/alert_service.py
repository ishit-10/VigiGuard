"""
Alert service for generating and managing PPE violation alerts.
"""
import os
import sys
import yaml
import json
import datetime
import time
from typing import Dict, List, Optional, Set, Tuple
from threading import Lock
from dataclasses import dataclass, field

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "backend", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


@dataclass
class AlertEvent:
    """Alert event data."""
    violation_type: str
    severity: str
    message: str
    person_track_id: Optional[int] = None
    camera_id: str = "camera_01"
    timestamp: float = 0.0
    detection_data: Optional[Dict] = None


class AlertService:
    """
    Alert management service.
    Handles alert generation, deduplication, cooldown, and persistence.
    """
    
    def __init__(self, db_session=None):
        """
        Initialize alert service.
        
        Args:
            db_session: Optional SQLAlchemy database session
        """
        self.db = db_session
        self.enabled = config['alert']['enabled']
        self.cooldown_seconds = config['alert']['cooldown_seconds']
        
        # Alert type configs
        self.alert_configs = config['alert']['alert_types']
        
        # Track last alert time per violation type per track_id
        self._last_alert_time: Dict[str, float] = {}
        self._lock = Lock()
        
        # Callbacks for external notification (webhook, email, etc.)
        self._alert_callbacks = []
        
        # Statistics
        self.stats = {
            'total_alerts': 0,
            'alerts_by_type': {},
            'alerts_by_severity': {},
            'last_alert_timestamp': 0,
        }
    
    def check_violations(self, violations: Dict[str, List], 
                         frame_id: int, timestamp: float,
                         camera_id: str = "camera_01",
                         detections: Optional[List] = None) -> List[AlertEvent]:
        """
        Check violations and generate alerts.
        
        Args:
            violations: Dict of violation_type -> list of Detection objects
            frame_id: Current frame ID
            timestamp: Frame timestamp
            camera_id: Camera identifier
            detections: Full list of detections for context
            
        Returns:
            List of new AlertEvent objects
        """
        if not self.enabled:
            return []
        
        new_alerts = []
        
        for violation_type, persons in violations.items():
            if violation_type not in self.alert_configs:
                continue
            
            alert_config = self.alert_configs[violation_type]
            severity = alert_config['severity']
            message_template = alert_config['message']
            
            for person in persons:
                # Check cooldown
                alert_key = f"{violation_type}_{person.track_id or 'unknown'}"
                current_time = time.time()
                
                with self._lock:
                    last_time = self._last_alert_time.get(alert_key, 0)
                    if current_time - last_time < self.cooldown_seconds:
                        continue
                    self._last_alert_time[alert_key] = current_time
                
                # Create alert event
                detection_data = None
                if detections:
                    # Include relevant detection context
                    detection_data = {
                        'frame_id': frame_id,
                        'person_bbox': list(person.bbox) if hasattr(person, 'bbox') else None,
                        'person_confidence': person.confidence if hasattr(person, 'confidence') else None,
                    }
                
                alert = AlertEvent(
                    violation_type=violation_type,
                    severity=severity,
                    message=f"{message_template} (Camera: {camera_id})",
                    person_track_id=person.track_id if hasattr(person, 'track_id') else None,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    detection_data=detection_data
                )
                
                new_alerts.append(alert)
                
                # Update stats
                with self._lock:
                    self.stats['total_alerts'] += 1
                    self.stats['alerts_by_type'][violation_type] = \
                        self.stats['alerts_by_type'].get(violation_type, 0) + 1
                    self.stats['alerts_by_severity'][severity] = \
                        self.stats['alerts_by_severity'].get(severity, 0) + 1
                    self.stats['last_alert_timestamp'] = current_time
        
        # Persist alerts and notify callbacks
        for alert in new_alerts:
            self._persist_alert(alert)
            self._notify_callbacks(alert)
        
        return new_alerts
    
    def _persist_alert(self, alert: AlertEvent):
        """Persist alert to database."""
        if self.db is None:
            return
        
        try:
            from backend.db.models import Alert, ViolationRecord
            
            # Create violation record
            violation = ViolationRecord(
                timestamp=datetime.datetime.fromtimestamp(alert.timestamp),
                violation_type=alert.violation_type,
                severity=alert.severity,
                person_track_id=alert.person_track_id,
                camera_id=alert.camera_id,
            )
            self.db.add(violation)
            self.db.flush()
            
            # Create alert
            db_alert = Alert(
                timestamp=datetime.datetime.fromtimestamp(alert.timestamp),
                violation_type=alert.violation_type,
                violation_id=violation.id,
                severity=alert.severity,
                status="active",
                message=alert.message,
                camera_id=alert.camera_id,
            )
            self.db.add(db_alert)
            self.db.commit()
        except Exception as e:
            print(f"Error persisting alert: {e}")
            self.db.rollback()
    
    def register_callback(self, callback):
        """Register callback for new alerts."""
        self._alert_callbacks.append(callback)
    
    def _notify_callbacks(self, alert: AlertEvent):
        """Notify all registered callbacks."""
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"Alert callback error: {e}")
    
    def acknowledge_alert(self, alert_id: int, acknowledged_by: str = "operator") -> bool:
        """Acknowledge an alert."""
        if self.db is None:
            return False
        
        try:
            from backend.db.models import Alert
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.status = "acknowledged"
                alert.acknowledged_at = datetime.datetime.utcnow()
                alert.acknowledged_by = acknowledged_by
                self.db.commit()
                return True
        except Exception as e:
            print(f"Error acknowledging alert: {e}")
            self.db.rollback()
        
        return False
    
    def resolve_alert(self, alert_id: int) -> bool:
        """Resolve an alert."""
        if self.db is None:
            return False
        
        try:
            from backend.db.models import Alert
            alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.status = "resolved"
                alert.resolved_at = datetime.datetime.utcnow()
                self.db.commit()
                return True
        except Exception as e:
            print(f"Error resolving alert: {e}")
            self.db.rollback()
        
        return False
    
    def get_active_alerts(self, limit: int = 50) -> List:
        """Get active alerts from database."""
        if self.db is None:
            return []
        
        try:
            from backend.db.models import Alert
            alerts = self.db.query(Alert).filter(
                Alert.status == "active"
            ).order_by(
                Alert.timestamp.desc()
            ).limit(limit).all()
            return alerts
        except Exception as e:
            print(f"Error fetching alerts: {e}")
            return []
    
    def get_alert_stats(self) -> Dict:
        """Get alert statistics."""
        with self._lock:
            return dict(self.stats)
    
    def set_database(self, db_session):
        """Set database session (for dependency injection)."""
        self.db = db_session