import React, { useState, useEffect } from 'react'
import {
  getSystemStatus,
  getMetricsSummary,
  getActiveAlerts,
  getLatestDetection,
  getComplianceHistory,
  getViolationsTrend,
} from '../services/api'

function StatCard({ title, value, subtitle, icon, color = 'primary' }) {
  const colorMap = {
    primary: 'bg-primary-500/10 text-primary-400 border-primary-500/20',
    success: 'bg-success-500/10 text-success-400 border-success-500/20',
    warning: 'bg-warning-500/10 text-warning-400 border-warning-500/20',
    danger: 'bg-danger-500/10 text-danger-400 border-danger-500/20',
  }
  return (
    <div className="card fade-in">
      <div className="card-body">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-slate-400">{title}</p>
            <p className="text-3xl font-bold text-white mt-1">{value}</p>
            {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
          </div>
          <div className={`p-3 rounded-lg border ${colorMap[color] || colorMap.primary}`}>
            {icon}
          </div>
        </div>
      </div>
    </div>
  )
}

function AlertItem({ alert }) {
  const severityColors = {
    high: 'border-l-danger-500',
    medium: 'border-l-warning-500',
    low: 'border-l-primary-500',
    critical: 'border-l-danger-500',
  }
  return (
    <div className={`border-l-4 ${severityColors[alert.severity] || 'border-l-slate-500'} bg-slate-800/30 px-4 py-3 rounded-r-lg fade-in`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-white">
            {alert.violation_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </p>
          <p className="text-xs text-slate-400 mt-0.5">
            {alert.message || 'PPE violation detected'} · {alert.camera_id}
          </p>
        </div>
        <span className={`status-badge status-badge-${alert.status}`}>
          {alert.status}
        </span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [status, setStatus] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [latestDetection, setLatestDetection] = useState(null)
  const [complianceHistory, setComplianceHistory] = useState([])
  const [violationsTrend, setViolationsTrend] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, metricsRes, alertsRes, detectionRes, complianceRes, trendRes] = await Promise.allSettled([
          getSystemStatus(),
          getMetricsSummary(),
          getActiveAlerts(),
          getLatestDetection(),
          getComplianceHistory(24),
          getViolationsTrend(24),
        ])

        if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data)
        if (metricsRes.status === 'fulfilled') setMetrics(metricsRes.value.data)
        if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value.data.alerts || [])
        if (detectionRes.status === 'fulfilled') setLatestDetection(detectionRes.value.data)
        if (complianceRes.status === 'fulfilled') setComplianceHistory(complianceRes.value.data.compliance_history || [])
        if (trendRes.status === 'fulfilled') setViolationsTrend(trendRes.value.data.violations_trend || [])
      } catch (err) {
        console.error('Dashboard fetch error:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-slate-400 text-sm">Loading dashboard data...</div>
      </div>
    )
  }

  const currentCompliance = metrics?.current_compliance_rate ?? status?.compliance_rate ?? 100
  const totalViolations = metrics?.total_violations_today ?? status?.total_violations_today ?? 0
  const activeAlerts = metrics?.total_alerts_active ?? status?.alerts_active ?? 0
  const currentWorkers = status?.persons_current ?? 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">PPE compliance monitoring overview</p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Compliance Rate"
          value={`${currentCompliance.toFixed(1)}%`}
          subtitle="Current shift"
          color={currentCompliance >= 90 ? 'success' : currentCompliance >= 70 ? 'warning' : 'danger'}
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <StatCard
          title="Violations Today"
          value={totalViolations}
          subtitle="Total recorded"
          color={totalViolations === 0 ? 'success' : totalViolations < 10 ? 'warning' : 'danger'}
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>}
        />
        <StatCard
          title="Active Alerts"
          value={activeAlerts}
          subtitle="Requiring attention"
          color={activeAlerts === 0 ? 'success' : activeAlerts < 5 ? 'warning' : 'danger'}
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>}
        />
        <StatCard
          title="Current Workers"
          value={currentWorkers}
          subtitle="In frame"
          color="primary"
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>}
        />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Violations by Type */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Violations by Type</h3>
          </div>
          <div className="card-body">
            {metrics?.violations_by_type && Object.keys(metrics.violations_by_type).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(metrics.violations_by_type).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-slate-300 capitalize">
                      {type.replace(/_/g, ' ')}
                    </span>
                    <div className="flex items-center gap-3">
                      <div className="w-32 h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-danger-500 rounded-full"
                          style={{ width: `${Math.min(100, (count / Math.max(...Object.values(metrics.violations_by_type))) * 100)}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-slate-200 w-8 text-right">{count}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No violations recorded today</p>
            )}
          </div>
        </div>

        {/* Recent Alerts */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Recent Alerts</h3>
          </div>
          <div className="card-body space-y-2">
            {alerts.length > 0 ? (
              alerts.slice(0, 5).map((alert) => (
                <AlertItem key={alert.id} alert={alert} />
              ))
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No active alerts</p>
            )}
          </div>
        </div>
      </div>

      {/* Compliance & Violations Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Compliance History */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Compliance Rate History</h3>
          </div>
          <div className="card-body">
            {complianceHistory.length > 0 ? (
              <div className="space-y-1">
                {complianceHistory.slice(-10).map((item, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs">
                    <span className="text-slate-500 w-16">
                      {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <div className="flex-1 h-3 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          item.compliance_rate >= 90 ? 'bg-success-500' :
                          item.compliance_rate >= 70 ? 'bg-warning-500' : 'bg-danger-500'
                        }`}
                        style={{ width: `${item.compliance_rate}%` }}
                      />
                    </div>
                    <span className="text-slate-300 w-12 text-right font-medium">
                      {item.compliance_rate.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No historical data yet</p>
            )}
          </div>
        </div>

        {/* Violations Trend */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Violations Trend</h3>
          </div>
          <div className="card-body">
            {violationsTrend.length > 0 ? (
              <div className="space-y-1">
                {violationsTrend.slice(-10).map((item, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs">
                    <span className="text-slate-500 w-16">
                      {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <div className="flex-1 flex gap-1">
                      <div className="h-3 bg-danger-500/20 rounded" style={{ width: `${(item.no_helmet || 0) * 20}px` }} title="No Helmet" />
                      <div className="h-3 bg-warning-500/20 rounded" style={{ width: `${(item.no_gloves || 0) * 20}px` }} title="No Gloves" />
                      <div className="h-3 bg-primary-500/20 rounded" style={{ width: `${(item.no_shoes || 0) * 20}px` }} title="No Shoes" />
                      <div className="h-3 bg-purple-500/20 rounded" style={{ width: `${(item.no_safety_suit || 0) * 20}px` }} title="No Safety Suit" />
                    </div>
                    <span className="text-slate-400 w-6 text-right">{item.total || 0}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No trend data available</p>
            )}
          </div>
        </div>
      </div>

      {/* System Status */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-white">System Status</h3>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                status?.status === 'running' ? 'bg-success-500/20 text-success-400' : 'bg-slate-500/20 text-slate-400'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${status?.status === 'running' ? 'bg-success-400' : 'bg-slate-400'}`} />
                {status?.status || 'unknown'}
              </div>
              <p className="text-xs text-slate-500 mt-2">Pipeline Status</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-semibold text-white">{status?.fps?.toFixed(1) || '0.0'}</p>
              <p className="text-xs text-slate-500 mt-1">Processing FPS</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-semibold text-white">{status?.avg_inference_ms?.toFixed(1) || '0'}ms</p>
              <p className="text-xs text-slate-500 mt-1">Inference Time</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-semibold text-white">{status?.uptime_seconds ? Math.floor(status.uptime_seconds / 60) : 0}m</p>
              <p className="text-xs text-slate-500 mt-1">Uptime</p>
            </div>
          </div>
        </div>
      </div>

      {/* Latest Detection */}
      {latestDetection && latestDetection.status !== 'no_data' && (
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Latest Detection Snapshot</h3>
          </div>
          <div className="card-body">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-slate-500">Timestamp</p>
                <p className="text-sm text-slate-200">
                  {new Date(latestDetection.timestamp).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Persons Detected</p>
                <p className="text-sm text-slate-200">{latestDetection.person_count}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Total Objects</p>
                <p className="text-sm text-slate-200">{latestDetection.total_detections}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Inference</p>
                <p className="text-sm text-slate-200">{latestDetection.inference_time_ms?.toFixed(1)}ms</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}