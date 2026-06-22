"""
WebSocket endpoints for real-time streaming of detection data and alerts.
"""
import os
import sys
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Dict
import time

router = APIRouter()


class ConnectionManager:
    """WebSocket connection manager."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            'detections': set(),
            'alerts': set(),
            'metrics': set(),
            'all': set(),
        }
    
    async def connect(self, websocket: WebSocket, channels: list = None):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        
        if channels is None:
            channels = ['all']
        
        for channel in channels:
            if channel in self.active_connections:
                self.active_connections[channel].add(websocket)
        
        # Always add to 'all'
        self.active_connections['all'].add(websocket)
    
    def disconnect(self, websocket: WebSocket, channels: list = None):
        """Remove a WebSocket connection."""
        for channel in self.active_connections:
            if websocket in self.active_connections[channel]:
                self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, message: dict, channel: str = 'all'):
        """Broadcast a message to all connections in a channel."""
        dead_connections = set()
        
        for connection in self.active_connections.get(channel, set()):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.add(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time data streaming."""
    channels = ['detections', 'alerts', 'metrics']
    await manager.connect(websocket, channels)
    
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle subscription changes
                if 'subscribe' in message:
                    channels_to_add = message['subscribe']
                    if isinstance(channels_to_add, list):
                        for ch in channels_to_add:
                            if ch in manager.active_connections:
                                manager.active_connections[ch].add(websocket)
                
                if 'unsubscribe' in message:
                    channels_to_remove = message['unsubscribe']
                    if isinstance(channels_to_remove, list):
                        for ch in channels_to_remove:
                            if ch in manager.active_connections and websocket in manager.active_connections[ch]:
                                manager.active_connections[ch].remove(websocket)
                
                # Send acknowledgment
                await websocket.send_json({
                    'type': 'connection_ack',
                    'timestamp': time.time(),
                    'message': 'Connected to DMRC PPE Tracking System'
                })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    'type': 'error',
                    'message': 'Invalid JSON'
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_detection(detection_data: dict):
    """Broadcast detection data to WebSocket clients."""
    await manager.broadcast({
        'type': 'detection',
        'data': detection_data,
        'timestamp': time.time()
    }, channel='detections')


async def broadcast_alert(alert_data: dict):
    """Broadcast alert data to WebSocket clients."""
    await manager.broadcast({
        'type': 'alert',
        'data': alert_data,
        'timestamp': time.time()
    }, channel='alerts')


async def broadcast_metrics(metrics_data: dict):
    """Broadcast metrics update to WebSocket clients."""
    await manager.broadcast({
        'type': 'metrics',
        'data': metrics_data,
        'timestamp': time.time()
    }, channel='metrics')