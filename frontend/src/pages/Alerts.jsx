import React, { useState, useEffect } from 'react'
import { getAlerts, acknowledgeAlert, resolveAlert } from '../services/api'

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [total, setTotal] = useState(0)

  const fetchAlerts = async () => {
    try {
      const params = { limit: 100 }
      if (filter !== 'all') params.status = filter
      const res = await getAlerts(params)
      setAlerts(res.data.alerts)
      setTotal(res.data.total)
    } catch (err) {
      console.error('Failed to fetch alerts:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 15000)
    return () => clearInterval(interval)
  }, [filter])

  const handleAcknowledge = async (id) => {
    try {
      await acknowledgeAlert(id, 'operator')
      fetchAlerts()
    } catch (err) {
      console.error('Failed to acknowledge:', err)
    }
  }

  const handleResolve = async (id) => {
    try {
      await resolveAlert(id)
      fetchAlerts()
    } catch (err) {
      console.error('Failed to resolve:', err)
    }
  }

  const severityColors = {
    critical: 'bg-danger-500/20 text-danger-400',
    high: 'bg-danger-500/15 text-danger-400',
    medium: 'bg-warning-500/20 text-warning-400',
    low: 'bg-primary-500/20 text-primary-400',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
          <p className="text-sm text-slate-400 mt-1">PPE violation alerts management</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">Total: {total}</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {['all', 'active', 'acknowledged', 'resolved'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === f
                ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                : 'bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:bg-slate-700/50'
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Alerts List */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-slate-400 text-sm">Loading alerts...</p>
        </div>
      ) : alerts.length === 0 ? (
        <div className="card">
          <div className="card-body text-center py-12">
            <svg className="w-12 h-12 mx-auto text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-slate-400">No alerts found</p>
            <p className="text-xs text-slate-500 mt-1">All clear - no PPE violations detected</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div key={alert.id} className="card fade-in">
              <div className="card-body">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${severityColors[alert.severity] || 'bg-slate-500/20 text-slate-400'}`}>
                        {alert.severity}
                      </span>
                      <span className={`status-badge status-badge-${alert.status}`}>
                        {alert.status}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(alert.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-white mt-2 capitalize">
                      {alert.violation_type.replace(/_/g, ' ')}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">{alert.message}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                      <span>Camera: {alert.camera_id}</span>
                      {alert.acknowledged_by && <span>Acknowledged by: {alert.acknowledged_by}</span>}
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    {(alert.status === 'active') && (
                      <button
                        onClick={() => handleAcknowledge(alert.id)}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium bg-warning-500/20 text-warning-400 border border-warning-500/30 hover:bg-warning-500/30 transition-all"
                      >
                        Acknowledge
                      </button>
                    )}
                    {(alert.status === 'active' || alert.status === 'acknowledged') && (
                      <button
                        onClick={() => handleResolve(alert.id)}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium bg-success-500/20 text-success-400 border border-success-500/30 hover:bg-success-500/30 transition-all"
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}