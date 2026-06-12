'use client'
// File: frontend/src/app/admin/analytics/page.tsx

import { useState, useEffect } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Overview {
  total: number; open: number; in_progress: number; resolved: number
  this_week: number; this_month: number; sla_compliance: number
  sla_breached: number; ai_resolution_rate: number
}
interface DomainStat { domain: string; label: string; total: number; resolved: number; open: number }
interface PriorityStat { priority: string; total: number; resolved: number; color: string }
interface TimeStat { date: string; label: string; created: number; resolved: number }

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .ovw *{box-sizing:border-box;margin:0;padding:0}
  .ovw{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .ovw .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .ovw .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:10px;min-height:40px}
  .ovw .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .ovw .stat-lbl{font-size:10px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.08em;font-family:"JetBrains Mono",monospace;font-weight:600}
  .ovw .stat-v{font-size:24px;font-weight:700;letter-spacing:-.02em;line-height:1.1;margin-top:5px;font-feature-settings:"tnum";font-family:"JetBrains Mono",monospace}
  .ovw .stat-d{font-size:11px;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-top:3px}
  .ovw .stat-d.up{color:#1a7a4a}.ovw .stat-d.dn{color:#4D1717}
  .ovw .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .ovw .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .ovw .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .ovw .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .ovw .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .ovw .bar-wrap{height:5px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
  .ovw .bar-fill{height:100%;transition:width .4s;border-radius:3px}
  .ovw .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
  .ovw .dot-ok{background:#1a7a4a}.ovw .dot-warn{background:#8a5a00}.ovw .dot-crit{background:#4D1717}.ovw .dot-grn{background:#174D38}
  .ovw table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .ovw table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .ovw table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .ovw .mono{font-family:"JetBrains Mono",monospace}
  .ovw .muted{color:#6b6b6b}
  .ovw .small{font-size:11px}
  .ovw .tiny{font-size:10px}
  .ovw .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ovw .sec-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace}
`

export default function OverviewPage() {
  const [overview, setOverview]     = useState<Overview | null>(null)
  const [domains, setDomains]       = useState<DomainStat[]>([])
  const [priorities, setPriorities] = useState<PriorityStat[]>([])
  const [timeSeries, setTimeSeries] = useState<TimeStat[]>([])
  const [loading, setLoading]       = useState(true)
  const [timeRange, setTimeRange]   = useState(30)

  const hdrs = () => ({ Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}` })

  useEffect(() => { fetchAll() }, [timeRange])

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [oR, dR, pR, tR] = await Promise.all([
        fetch(`${API}/api/v1/analytics/overview`, { headers: hdrs() }),
        fetch(`${API}/api/v1/analytics/by-domain`, { headers: hdrs() }),
        fetch(`${API}/api/v1/analytics/by-priority`, { headers: hdrs() }),
        fetch(`${API}/api/v1/analytics/over-time?days=${timeRange}`, { headers: hdrs() }),
      ])
      if (oR.ok) setOverview(await oR.json())
      if (dR.ok) setDomains(await dR.json())
      if (pR.ok) setPriorities(await pR.json())
      if (tR.ok) setTimeSeries(await tR.json())
    } catch {}
    finally { setLoading(false) }
  }

  const maxDomain = Math.max(...domains.map(d => d.total), 1)
  const maxTime   = Math.max(...timeSeries.map(d => Math.max(d.created, d.resolved)), 1)

  const pColor = (p: string) =>
    p === 'critical' ? '#4D1717' : p === 'high' ? '#8a5a00' : p === 'medium' ? '#174D38' : '#6b6b6b'
  const pPillClass = (p: string) =>
    p === 'critical' ? 'pill-crit' : p === 'high' ? 'pill-warn' : p === 'medium' ? 'pill-grn' : ''

  return (
    <>
      <style>{CSS}</style>
      <div className="ovw" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-.01em' }}>Overview</div>
            <div className="small muted">Platform performance · live data</div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setTimeRange(d)} style={{ height: 28, padding: '0 10px', borderRadius: 4, border: `1px solid ${timeRange === d ? '#174D38' : '#CBCBCB'}`, background: timeRange === d ? '#174D38' : '#fff', color: timeRange === d ? '#fff' : '#6b6b6b', fontFamily: 'inherit', fontSize: 12, fontWeight: 500, cursor: 'pointer' }}>
                {d}d
              </button>
            ))}
            <button onClick={fetchAll} style={{ height: 28, padding: '0 10px', borderRadius: 4, border: '1px solid #CBCBCB', background: '#e8f2ed', color: '#174D38', fontFamily: 'inherit', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>↻</button>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: '#6b6b6b', fontSize: 13 }}>Loading...</div>
        ) : (
          <>
            {/* KPI row — 5 cards */}
            {overview && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
                {[
                  { l: 'AI Resolution',    v: `${overview.ai_resolution_rate}%`, d: 'of resolved tickets', du: 'up' },
                  { l: 'Open Tickets',     v: overview.open,                       d: `${overview.in_progress} in progress`, du: '' },
                  { l: 'Total Tickets',    v: overview.total,                      d: `${overview.this_week} this week`, du: '' },
                  { l: 'Avg Resolution',   v: '—',                                 d: 'check resolution tab', du: '' },
                  { l: 'SLA Compliance',   v: `${overview.sla_compliance}%`,       d: `${overview.sla_breached} breached`, du: overview.sla_compliance >= 90 ? 'up' : 'dn' },
                ].map((s, i) => (
                  <div key={i} className="card" style={{ padding: '14px 16px', position: 'relative', overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: i === 0 ? '#174D38' : i === 4 ? (overview.sla_compliance >= 90 ? '#1a7a4a' : '#4D1717') : '#CBCBCB' }} />
                    <div className="stat-lbl">{s.l}</div>
                    <div className="stat-v">{s.v}</div>
                    <div className={`stat-d ${s.du}`}>{s.d}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Volume chart + Priority donut */}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>

              {/* Volume bar chart */}
              <div className="card">
                <div className="c-head">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                  <h3>Ticket Volume · last {timeRange} days</h3>
                </div>
                <div style={{ padding: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 100 }}>
                    {timeSeries.map((d, i) => (
                      <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 1, height: '100%' }}>
                        <div title={`${d.label}: ${d.resolved} resolved`} style={{ background: '#1a7a4a', borderRadius: '1px 1px 0 0', height: `${(d.resolved / maxTime) * 80}px`, minHeight: d.resolved > 0 ? 2 : 0 }} />
                        <div title={`${d.label}: ${d.created} created`} style={{ background: '#174D38', borderRadius: '1px 1px 0 0', height: `${(d.created / maxTime) * 80}px`, minHeight: d.created > 0 ? 2 : 0, opacity: 0.4 }} />
                      </div>
                    ))}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
                    {timeSeries.filter((_, i) => i % Math.ceil(timeSeries.length / 7) === 0).map((d, i) => (
                      <span key={i} className="tiny muted mono">{d.label}</span>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
                    {[{ c: 'rgba(23,77,56,0.4)', l: 'Created' }, { c: '#1a7a4a', l: 'Resolved' }].map((x, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <div style={{ width: 10, height: 10, background: x.c, borderRadius: 2 }} />
                        <span className="tiny muted">{x.l}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Priority breakdown */}
              <div className="card">
                <div className="c-head">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  <h3>By Priority</h3>
                </div>
                <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {priorities.map(p => {
                    const total = priorities.reduce((s, x) => s + x.total, 1)
                    return (
                      <div key={p.priority}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                          <span className={`pill ${pPillClass(p.priority)}`}>{p.priority}</span>
                          <span className="small mono muted">{p.total} ({Math.round(p.total / total * 100)}%)</span>
                        </div>
                        <div className="bar-wrap">
                          <div className="bar-fill" style={{ width: `${p.total / total * 100}%`, background: pColor(p.priority) }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* Domain breakdown + Status */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

              {/* Domain table */}
              <div className="card">
                <div className="c-head">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                  <h3>Tickets by Domain</h3>
                </div>
                <table className="dt">
                  <thead><tr><th>Domain</th><th>Total</th><th>Open</th><th>Resolved</th><th>Load</th></tr></thead>
                  <tbody>
                    {domains.sort((a, b) => b.total - a.total).map(d => (
                      <tr key={d.domain}>
                        <td style={{ fontWeight: 500 }}>{d.label}</td>
                        <td className="mono" style={{ fontWeight: 600 }}>{d.total}</td>
                        <td><span className="pill pill-warn">{d.open}</span></td>
                        <td><span className="pill pill-ok">{d.resolved}</span></td>
                        <td style={{ width: 80 }}>
                          <div className="bar-wrap">
                            <div className="bar-fill" style={{ width: `${(d.total / maxDomain) * 100}%`, background: '#174D38' }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Status + month summary */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

                {/* Status breakdown */}
                {overview && (
                  <div className="card">
                    <div className="c-head">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>
                      <h3>Status Breakdown</h3>
                    </div>
                    <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {[
                        { l: 'Open',        v: overview.open,        k: 'pill-warn', bar: '#8a5a00' },
                        { l: 'In Progress', v: overview.in_progress, k: 'pill-grn',  bar: '#174D38' },
                        { l: 'Resolved',    v: overview.resolved,    k: 'pill-ok',   bar: '#1a7a4a' },
                      ].map(s => (
                        <div key={s.l}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span className={`pill ${s.k}`}>{s.l}</span>
                            <span className="small mono" style={{ fontWeight: 600 }}>{s.v}</span>
                          </div>
                          <div className="bar-wrap">
                            <div className="bar-fill" style={{ width: `${overview.total > 0 ? (s.v / overview.total) * 100 : 0}%`, background: s.bar }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Volume summary */}
                {overview && (
                  <div className="card">
                    <div className="c-head">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                      <h3>Volume Summary</h3>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: '#CBCBCB' }}>
                      {[
                        { l: 'This Week',  v: overview.this_week },
                        { l: 'This Month', v: overview.this_month },
                        { l: 'Total',      v: overview.total },
                        { l: 'Resolved',   v: overview.resolved },
                      ].map((s, i) => (
                        <div key={i} style={{ background: '#fff', padding: '12px 14px' }}>
                          <div className="stat-lbl">{s.l}</div>
                          <div style={{ fontSize: 22, fontWeight: 700, fontFamily: '"JetBrains Mono",monospace', letterSpacing: '-.02em', marginTop: 4 }}>{s.v}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}