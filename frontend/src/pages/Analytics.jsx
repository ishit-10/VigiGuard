import React, { useState, useEffect } from 'react'
import { getMetricsSummary, getComplianceHistory, getViolationsTrend, getMetricSnapshots } from '../services/api'

export default function Analytics() {
  const [summary, setSummary] = useState(null)
  const [complianceHistory, setComplianceHistory] = useState([])
  const [violationsTrend, setViolationsTrend] = useState([])
  const [snapshots, setSnapshots] = useState([])
  const [timeRange, setTimeRange] = useState(24)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryRes, complianceRes, trendRes, snapshotsRes] = await Promise.allSettled([
          getMetricsSummary(),
          getComplianceHistory(timeRange),
          getViolationsTrend(timeRange),
          getMetricSnapshots({ limit: 50 }),
        ])
        if (summaryRes.status === 'fulfilled') setSummary(summaryRes.value.data)
        if (complianceRes.status === 'fulfilled') setComplianceHistory(complianceRes.value.data.compliance_history || [])
        if (trendRes.status === 'fulfilled') setViolationsTrend(trendRes.value.data.violations_trend || [])
        if (snapshotsRes.status === 'fulfilled') setSnapshots(snapshotsRes.value.data.snapshots || [])
      } catch (err) {
        console.error('Analytics fetch error:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [timeRange])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-slate-400 text-sm">Loading analytics data...</p>
      </div>
    )
  }

  // Calculate totals from violations_trend
  const totalByType = { no_helmet: 0, no_gloves: 0, no_shoes: 0, no_safety_suit: 0 }
  violationsTrend.forEach(item => {
    totalByType.no_helmet += item.no_helmet || 0
    totalByType.no_gloves += item.no_gloves || 0
    totalByType.no_shoes += item.no_shoes || 0
    totalByType.no_safety_suit += item.no_safety_suit || 0
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-sm text-slate-400 mt-1">PPE compliance analytics and reporting</p>
        </div>
        <div className="flex gap-2">
          {[6, 12, 24, 48].map(h => (
            <button
              key={h}
              onClick={() => setTimeRange(h)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                timeRange === h
                  ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                  : 'bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:bg-slate-700/50'
              }`}
            >
              {h}h
            </button>
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="card">
            <div className="card-body text-center">
              <p className="text-2xl font-bold text-white">{summary.current_compliance_rate.toFixed(1)}%</p>
              <p className="text-xs text-slate-400 mt-1">Compliance Rate</p>
            </div>
          </div>
          <div className="card">
            <div className="card-body text-center">
              <p className="text-2xl font-bold text-danger-400">{summary.total_violations_today}</p>
              <p className="text-xs text-slate-400 mt-1">Violations Today</p>
            </div>
          </div>
          <div className="card">
            <div className="card-body text-center">
              <p className="text-2xl font-bold text-warning-400">{summary.total_alerts_active}</p>
              <p className="text-xs text-slate-400 mt-1">Active Alerts</p>
            </div>
          </div>
          <div className="card">
            <div className="card-body text-center">
              <p className="text-2xl font-bold text-white">{summary.total_persons_tracked}</p>
              <p className="text-xs text-slate-400 mt-1">Persons Tracked</p>
            </div>
          </div>
        </div>
      )}

      {/* Violations Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Violations by Type */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Violations Breakdown by Type</h3>
          </div>
          <div className="card-body">
            <div className="space-y-4">
              {[
                { key: 'no_helmet', label: 'No Helmet', color: 'bg-danger-500', count: totalByType.no_helmet },
                { key: 'no_gloves', label: 'No Gloves', color: 'bg-warning-500', count: totalByType.no_gloves },
                { key: 'no_shoes', label: 'No Safety Shoes', color: 'bg-primary-500', count: totalByType.no_shoes },
                { key: 'no_safety_suit', label: 'No Safety Suit', color: 'bg-purple-500', count: totalByType.no_safety_suit },
              ].map(item => {
                const maxVal = Math.max(totalByType.no_helmet, totalByType.no_gloves, totalByType.no_shoes, totalByType.no_safety_suit, 1)
                return (
                  <div key={item.key}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-slate-300">{item.label}</span>
                      <span className="text-slate-400 font-medium">{item.count}</span>
                    </div>
                    <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${item.color}`}
                        style={{ width: `${(item.count / maxVal) * 100}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Alerts by Severity */}
        <div className="card">
          <div className="card-header">
            <h3 className="text-sm font-semibold text-white">Alerts by Severity</h3>
          </div>
          <div className="card-body">
            {summary?.alerts_by_severity && Object.keys(summary.alerts_by_severity).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(summary.alerts_by_severity).map(([severity, count]) => (
                  <div key={severity}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-slate-300 capitalize">{severity}</span>
                      <span className="text-slate-400 font-medium">{count}</span>
                    </div>
                    <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          severity === 'critical' ? 'bg-danger-500' :
                          severity === 'high' ? 'bg-danger-400' :
                          severity === 'medium' ? 'bg-warning-500' : 'bg-primary-500'
                        }`}
                        style={{ width: `${(count / Math.max(...Object.values(summary.alerts_by_severity), 1)) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">No alerts by severity data</p>
            )}
          </div>
        </div>
      </div>

      {/* Compliance Trend */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-white">Compliance Rate Over Time</h3>
        </div>
        <div className="card-body">
          {complianceHistory.length > 0 ? (
            <div className="space-y-1">
              {complianceHistory.map((item, i) => (
                <div key={i} className="flex items-center gap-3 py-1">
                  <span className="text-xs text-slate-500 w-20">
                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <div className="flex-1 h-4 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        item.compliance_rate >= 90 ? 'bg-success-500' :
                        item.compliance_rate >= 70 ? 'bg-warning-500' : 'bg-danger-500'
                      }`}
                      style={{ width: `${item.compliance_rate}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-300 w-16 text-right font-medium">
                    {item.compliance_rate.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500 text-center py-8">No compliance history data available</p>
          )}
        </div>
      </div>

      {/* Recent Snapshots Table */}
      <div className="card">
        <div className="card-header">
          <h3 className="text-sm font-semibold text-white">Metrics Snapshots</h3>
        </div>
        <div className="card-body">
          {snapshots.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-700/50">
                    <th className="pb-2 font-medium">Time</th>
                    <th className="pb-2 font-medium">Persons</th>
                    <th className="pb-2 font-medium">Violations</th>
                    <th className="pb-2 font-medium">Compliance</th>
                    <th className="pb-2 font-medium">Inference</th>
                    <th className="pb-2 font-medium">Alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshots.slice(0, 20).map((snap) => (
                    <tr key={snap.id} className="border-b border-slate-800/50 text-slate-300">
                      <td className="py-2 text-xs text-slate-500">
                        {new Date(snap.timestamp).toLocaleTimeString()}
                      </td>
                      <td className="py-2">{snap.peak_person_count}</td>
                      <td className="py-2">
                        <span className={snap.total_violations > 0 ? 'text-danger-400' : 'text-success-400'}>
                          {snap.total_violations}
                        </span>
                      </td>
                      <td className="py-2">
                        <span className={
                          snap.compliance_rate >= 90 ? 'text-success-400' :
                          snap.compliance_rate >= 70 ? 'text-warning-400' : 'text-danger-400'
                        }>
                          {snap.compliance_rate.toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-2 text-xs text-slate-500">{snap.avg_inference_ms.toFixed(1)}ms</td>
                      <td className="py-2">{snap.alerts_generated}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500 text-center py-8">No metrics snapshots available</p>
          )}
        </div>
      </div>
    </div>
  )
}