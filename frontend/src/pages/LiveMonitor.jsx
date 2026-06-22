import React, { useState, useEffect, useRef } from 'react'
import { getSystemStatus, getLatestDetection } from '../services/api'

export default function LiveMonitor() {
  const [status, setStatus] = useState(null)
  const [latestDetection, setLatestDetection] = useState(null)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    // Connect to WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/live`
    
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      
      ws.onopen = () => {
        setWsConnected(true)
        ws.send(JSON.stringify({ subscribe: ['detections', 'alerts', 'metrics'] }))
      }
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'detection') {
            setLatestDetection(data.data)
          }
        } catch (e) {}
      }
      
      ws.onclose = () => setWsConnected(false)
      ws.onerror = () => setWsConnected(false)
    } catch (e) {
      console.error('WebSocket connection failed:', e)
    }
    
    // Fallback polling
    const interval = setInterval(async () => {
      try {
        const [statusRes, detectionRes] = await Promise.allSettled([
          getSystemStatus(),
          getLatestDetection(),
        ])
        if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data)
        if (detectionRes.status === 'fulfilled') setLatestDetection(detectionRes.value.data)
      } catch (e) {}
    }, 5000)
    
    return () => {
      clearInterval(interval)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Live Monitor</h1>
          <p className="text-sm text-slate-400 mt-1">Real-time PPE detection feed</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-success-400' : 'bg-slate-500'}`} />
          <span className="text-xs text-slate-400">
            {wsConnected ? 'WebSocket Connected' : 'Polling Mode'}
          </span>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <div className="card-body text-center">
            <p className="text-xs text-slate-400">Status</p>
            <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium mt-2 ${
              status?.status === 'running' ? 'bg-success-500/20 text-success-400' : 'bg-slate-500/20 text-slate-400'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${status?.status === 'running' ? 'bg-success-400' : 'bg-slate-400'}`} />
              {status?.status || 'unknown'}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body text-center">
            <p className="text-xs text-slate-400">Workers</p>
            <p className="text-2xl font-bold text-white mt-1">{latestDetection?.person_count || status?.persons_current || 0}</p>
          </div>
        </div>
        <div className="card">
          <div className="card-body text-center">
            <p className="text-xs text-slate-400">FPS</p>
            <p className="text-2xl font-bold text-white mt-1">{status?.fps?.toFixed(1) || '0.0'}</p>
          </div>
        </div>
        <div className="card">
          <div className="card-body text-center">
            <p className="text-xs text-slate-400">Inference</p>
            <p className="text-2xl font-bold text-white mt-1">{status?.avg_inference_ms?.toFixed(1) || '0'}ms</p>
          </div>
        </div>
      </div>

      {/* Video Feed Area */}
      <div className="card">
        <div className="card-header">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Camera Feed</h3>
            <div className="flex items-center gap-2">
              {status?.status === 'running' && (
                <span className="flex items-center gap-1.5 text-xs text-success-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-success-400 animate-pulse" />
                  LIVE
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="card-body">
          <div className="aspect-video bg-slate-900 rounded-lg border border-slate-700/50 flex items-center justify-center">
            {latestDetection?.detections ? (
              <div className="text-center p-8">
                <svg className="w-16 h-16 mx-auto text-slate-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                <p className="text-sm text-slate-400">
                  Detection pipeline is {status?.status === 'running' ? 'running' : 'stopped'}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  {latestDetection.person_count > 0
                    ? `${latestDetection.person_count} worker(s) detected in current frame`
                    : 'No persons detected in current frame'}
                </p>
                <div className="mt-4 flex justify-center gap-4">
                  <div className="text-xs">
                    <span className="text-slate-500">Objects:</span>
                    <span className="text-slate-200 ml-1">{latestDetection.total_detections || 0}</span>
                  </div>
                  <div className="text-xs">
                    <span className="text-slate-500">Violations:</span>
                    <span className="text-danger-400 ml-1">
                      {latestDetection.violations
                        ? Object.values(latestDetection.violations).reduce((a, b) => a + (b?.length || 0), 0)
                        : 0}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center p-8">
                <svg className="w-16 h-16 mx-auto text-slate-600 mb-4 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                <p className="text-sm text-slate-500">Waiting for camera feed...</p>
                <p className="text-xs text-slate-600 mt-1">Connect a camera in the Cameras page</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Detection Details */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-white">Current Frame Detections</h3>
        </div>
        <div className="card-body">
          {latestDetection?.detections && latestDetection.detections.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-700/50">
                    <th className="pb-2 font-medium">Class</th>
                    <th className="pb-2 font-medium">Confidence</th>
                    <th className="pb-2 font-medium">Bounding Box</th>
                    <th className="pb-2 font-medium">Track ID</th>
                  </tr>
                </thead>
                <tbody>
                  {latestDetection.detections.map((det, i) => (
                    <tr key={i} className="border-b border-slate-800/50 text-slate-300">
                      <td className="py-2 capitalize">{det.class_name}</td>
                      <td className="py-2">{(det.confidence * 100).toFixed(1)}%</td>
                      <td className="py-2 text-xs text-slate-500">
                        [{det.bbox?.join(', ')}]
                      </td>
                      <td className="py-2">{det.track_id || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500 text-center py-8">
              {status?.status === 'running' ? 'No detections in current frame' : 'Detection pipeline not active'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}