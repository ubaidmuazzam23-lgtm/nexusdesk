'use client'
// File: frontend/src/app/admin/routing-simulator/page.tsx

import { useState, useCallback, useEffect } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

const DOMAINS = [
  'networking', 'security', 'cloud', 'hardware', 'software',
  'database', 'devops', 'infrastructure', 'identity_access',
  'email_communication', 'erp_business_apps', 'endpoint_management'
]

const SEVERITIES = ['low', 'medium', 'high', 'critical']

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500;600&display=swap');
.rs *{box-sizing:border-box;margin:0;padding:0}
.rs{font-family:"DM Sans",-apple-system,sans-serif;font-size:13px;color:#111;min-height:100vh}
.rs .card{background:#fff;border:1px solid #e5e5e5;border-radius:8px}
.rs .mono{font-family:"DM Mono",monospace}
.rs .muted{color:#888}
.rs label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#888;font-family:"DM Mono",monospace;display:block;margin-bottom:5px}
.rs select{width:100%;padding:8px 10px;border:1px solid #e5e5e5;border-radius:5px;font-family:inherit;font-size:13px;color:#111;background:#fff;outline:none;transition:border-color .15s}
.rs select:focus{border-color:#111}
.rs .btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:36px;padding:0 16px;border-radius:5px;border:none;font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;width:100%}
.rs .btn-primary{background:#111;color:#fff}
.rs .btn-primary:hover{background:#333}
.rs .btn-primary:disabled{background:#ccc;cursor:not-allowed}
.rs .tag{display:inline-flex;align-items:center;height:20px;padding:0 8px;border-radius:10px;font-size:10px;font-weight:600;font-family:"DM Mono",monospace;text-transform:uppercase;letter-spacing:.04em}
.rs .tag-green{background:#f0fdf4;color:#16a34a}
.rs .tag-blue{background:#eff6ff;color:#2563eb}
.rs .tag-orange{background:#fffbeb;color:#d97706}
.rs .tag-red{background:#fef2f2;color:#dc2626}
.rs .tag-gray{background:#f3f4f6;color:#6b7280}
.rs .pulse{animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.rs .spin{animation:spin 1s linear infinite}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.rs .fade{animation:fade .4s ease-out}
@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
`

interface DBUser {
  id: string
  name: string
  email: string
  city: string
  country: string
  timezone: string
}

interface Engineer {
  engineer_id: string
  name: string
  city: string
  country: string
  timezone: string
  domain: string
  active_tickets: number
  max_capacity: number
  score: number
  score_breakdown: {
    domain_match: number
    timezone_score: number
    workload_score: number
    tz_diff_hours: number
  }
}

interface RoutingResult {
  assigned_engineer: Engineer | null
  all_candidates: Engineer[]
  routing_reason: string
  user_city: string
  user_timezone: string
  domain: string
  severity: string
  timestamp: string
}

export default function RoutingSimulatorPage() {
  const [domain, setDomain]           = useState('networking')
  const [severity, setSeverity]       = useState('high')
  const [loading, setLoading]         = useState(false)
  const [result, setResult]           = useState<RoutingResult | null>(null)
  const [error, setError]             = useState('')
  const [history, setHistory]         = useState<RoutingResult[]>([])
  const [users, setUsers]             = useState<DBUser[]>([])
  const [selectedUser, setSelectedUser] = useState<DBUser | null>(null)
  const [usersLoading, setUsersLoading] = useState(true)

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    'Content-Type': 'application/json',
  }), [])

  useEffect(() => {
    fetch(`${API}/api/v1/routing/users`, { headers: hdrs() })
      .then(r => r.json())
      .then(data => {
        setUsers(data)
        if (data.length > 0) setSelectedUser(data[0])
      })
      .catch(() => {})
      .finally(() => setUsersLoading(false))
  }, [])

  const simulate = async () => {
    if (!selectedUser) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const r = await fetch(`${API}/api/v1/routing/simulate`, {
        method: 'POST',
        headers: hdrs(),
        body: JSON.stringify({
          domain,
          severity,
          user_timezone: selectedUser.timezone,
          user_city: selectedUser.city,
          user_country: selectedUser.country,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Simulation failed')
      const res: RoutingResult = { ...d, timestamp: new Date().toLocaleTimeString() }
      setResult(res)
      setHistory(h => [res, ...h].slice(0, 8))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const sevColor = (s: string) => s === 'critical' ? 'tag-red' : s === 'high' ? 'tag-orange' : s === 'medium' ? 'tag-blue' : 'tag-gray'
  const scoreColor = (score: number) => score >= 10 ? '#16a34a' : score >= 5 ? '#d97706' : '#dc2626'

  return (
    <>
      <style>{CSS}</style>
      <div className="rs">

        {/* Header */}
        <div style={{ background: '#fff', borderBottom: '1px solid #e5e5e5', padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-.02em' }}>Routing Simulator</div>
            <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>Test the smart routing engine — no real tickets, no tokens consumed</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#16a34a' }} className="pulse" />
            <span style={{ fontSize: 11, color: '#888', fontFamily: '"DM Mono",monospace' }}>Engine Online</span>
          </div>
        </div>

        <div style={{ padding: '20px 24px', display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20, alignItems: 'start' }}>

          {/* ── LEFT PANEL ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            {/* Input form */}
            <div className="card" style={{ padding: 18 }}>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 14 }}>Simulation Parameters</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

                {/* User selector from DB */}
                <div>
                  <label>User (from database)</label>
                  {usersLoading ? (
                    <div style={{ padding: '8px 10px', border: '1px solid #e5e5e5', borderRadius: 5, fontSize: 12, color: '#888' }}>Loading users...</div>
                  ) : users.length === 0 ? (
                    <div style={{ padding: '8px 10px', border: '1px solid #fecaca', borderRadius: 5, fontSize: 12, color: '#dc2626', background: '#fef2f2' }}>
                      No users found. Register users first.
                    </div>
                  ) : (
                    <select
                      value={selectedUser?.id || ''}
                      onChange={e => setSelectedUser(users.find(u => u.id === e.target.value) || null)}
                    >
                      {users.map(u => (
                        <option key={u.id} value={u.id}>
                          {u.name} — {u.city}, {u.country}
                        </option>
                      ))}
                    </select>
                  )}
                  {selectedUser && (
                    <div style={{ marginTop: 6, padding: '6px 8px', background: '#f9f9f9', borderRadius: 4 }}>
                      <div style={{ fontSize: 10, color: '#888', fontFamily: '"DM Mono",monospace' }}>
                        📍 {selectedUser.city}, {selectedUser.country}
                      </div>
                      <div style={{ fontSize: 10, color: '#888', fontFamily: '"DM Mono",monospace', marginTop: 2 }}>
                        🕐 {selectedUser.timezone}
                      </div>
                      <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>
                        ✉ {selectedUser.email}
                      </div>
                    </div>
                  )}
                </div>

                {/* Domain */}
                <div>
                  <label>Ticket Domain</label>
                  <select value={domain} onChange={e => setDomain(e.target.value)}>
                    {DOMAINS.map(d => (
                      <option key={d} value={d}>
                        {d.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Severity */}
                <div>
                  <label>Severity</label>
                  <select value={severity} onChange={e => setSeverity(e.target.value)}>
                    {SEVERITIES.map(s => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <button
                  className="btn btn-primary"
                  onClick={simulate}
                  disabled={loading || !selectedUser || users.length === 0}
                >
                  {loading
                    ? <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin"><circle cx="12" cy="12" r="10"/></svg>Simulating...</>
                    : '▶  Run Simulation'}
                </button>

                {error && (
                  <div style={{ padding: '8px 10px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 5, fontSize: 11, color: '#dc2626' }}>
                    {error}
                  </div>
                )}
              </div>
            </div>

            {/* Scoring formula */}
            <div className="card" style={{ padding: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 10, fontFamily: '"DM Mono",monospace', textTransform: 'uppercase', letterSpacing: '.07em', color: '#888' }}>
                Scoring Formula
              </div>
              {[
                { pts: '+10', label: 'Domain Match',      color: '#16a34a' },
                { pts: '+5',  label: 'Same Timezone',     color: '#2563eb' },
                { pts: '+3',  label: 'Within ±3 hrs',     color: '#2563eb' },
                { pts: '+1',  label: 'Within ±6 hrs',     color: '#2563eb' },
                { pts: '-1',  label: 'Per active ticket', color: '#dc2626' },
              ].map(f => (
                <div key={f.label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', borderBottom: '1px solid #f5f5f5' }}>
                  <span style={{ width: 28, fontSize: 11, fontWeight: 700, color: f.color, fontFamily: '"DM Mono",monospace', textAlign: 'right', flexShrink: 0 }}>{f.pts}</span>
                  <span style={{ fontSize: 11, color: '#555' }}>{f.label}</span>
                </div>
              ))}
            </div>

            {/* History */}
            {history.length > 0 && (
              <div className="card" style={{ padding: 14 }}>
                <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 10, fontFamily: '"DM Mono",monospace', textTransform: 'uppercase', letterSpacing: '.07em', color: '#888' }}>
                  Recent Simulations
                </div>
                {history.map((h, i) => (
                  <div
                    key={i}
                    onClick={() => setResult(h)}
                    style={{ padding: '6px 8px', borderRadius: 4, cursor: 'pointer', marginBottom: 4 }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f5f5f5')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 11, fontWeight: 600 }}>{h.domain.replace(/_/g, ' ')}</span>
                      <span style={{ fontSize: 10, color: '#888', fontFamily: '"DM Mono",monospace' }}>{h.timestamp}</span>
                    </div>
                    <div style={{ fontSize: 10, color: '#888', marginTop: 1 }}>
                      {h.user_city} → {h.assigned_engineer?.name || 'None'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── RIGHT PANEL ── */}
          <div>
            {!result && !loading && (
              <div className="card" style={{ padding: '60px 24px', textAlign: 'center' }}>
                <div style={{ fontSize: 36, marginBottom: 14 }}>🎯</div>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>Configure and run a simulation</div>
                <div style={{ fontSize: 12, color: '#888', maxWidth: 360, margin: '0 auto' }}>
                  Select a user from the database, choose a domain and severity, then click Run Simulation to see exactly who gets assigned and why.
                </div>
              </div>
            )}

            {result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} className="fade">

                {/* Winner card */}
                <div className="card" style={{ padding: 20, borderLeft: `4px solid ${result.assigned_engineer ? '#16a34a' : '#dc2626'}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 10, color: '#888', fontFamily: '"DM Mono",monospace', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 4 }}>
                        Routing Decision
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 700 }}>
                        {result.assigned_engineer ? `✓ ${result.assigned_engineer.name}` : '✗ No engineer available'}
                      </div>
                      {result.assigned_engineer && (
                        <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                          {result.assigned_engineer.city}, {result.assigned_engineer.country} · {result.assigned_engineer.timezone}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <span className={`tag ${sevColor(result.severity)}`}>{result.severity}</span>
                      <span className="tag tag-blue">{result.domain.replace(/_/g, ' ')}</span>
                    </div>
                  </div>

                  {result.assigned_engineer && (
                    <>
                      {/* Reason */}
                      <div style={{ padding: '10px 12px', background: '#f0fdf4', borderRadius: 6, fontSize: 12, color: '#16a34a', marginBottom: 14 }}>
                        💡 {result.routing_reason}
                      </div>

                      {/* Score breakdown */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
                        {[
                          { label: 'Domain',   value: result.assigned_engineer.score_breakdown.domain_match,   color: result.assigned_engineer.score_breakdown.domain_match > 0 ? '#16a34a' : '#dc2626', suffix: 'pts' },
                          { label: 'Timezone', value: result.assigned_engineer.score_breakdown.timezone_score, color: result.assigned_engineer.score_breakdown.timezone_score > 0 ? '#2563eb' : '#888',   suffix: 'pts' },
                          { label: 'TZ Diff',  value: result.assigned_engineer.score_breakdown.tz_diff_hours,  color: result.assigned_engineer.score_breakdown.tz_diff_hours === 0 ? '#16a34a' : result.assigned_engineer.score_breakdown.tz_diff_hours <= 3 ? '#d97706' : '#dc2626', suffix: 'hrs' },
                          { label: 'Workload', value: result.assigned_engineer.score_breakdown.workload_score, color: result.assigned_engineer.score_breakdown.workload_score >= 0 ? '#16a34a' : '#dc2626', suffix: 'pts' },
                        ].map(s => (
                          <div key={s.label} style={{ padding: '10px 12px', background: '#f9f9f9', borderRadius: 6, textAlign: 'center' }}>
                            <div style={{ fontSize: 9, color: '#888', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: '"DM Mono",monospace', marginBottom: 4 }}>{s.label}</div>
                            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: '"DM Mono",monospace', color: s.color }}>{s.value}</div>
                            <div style={{ fontSize: 9, color: '#aaa', fontFamily: '"DM Mono",monospace' }}>{s.suffix}</div>
                          </div>
                        ))}
                      </div>

                      {/* Total */}
                      <div style={{ marginTop: 12, padding: '10px 14px', background: '#f0fdf4', borderRadius: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#16a34a' }}>Total Routing Score</span>
                        <span style={{ fontSize: 22, fontWeight: 700, fontFamily: '"DM Mono",monospace', color: '#16a34a' }}>{result.assigned_engineer.score} pts</span>
                      </div>
                    </>
                  )}
                </div>

                {/* All candidates table */}
                {result.all_candidates.length > 0 && (
                  <div className="card" style={{ overflow: 'hidden' }}>
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>All Engineers Evaluated</div>
                      <span style={{ fontSize: 11, color: '#888' }}>{result.all_candidates.length} candidates · sorted by score</span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr>
                            {['#', 'Engineer', 'Location', 'Domain', 'TZ Diff', 'Workload', 'Score', 'Result'].map(h => (
                              <th key={h} style={{ textAlign: 'left', fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em', color: '#888', padding: '8px 14px', background: '#fafafa', borderBottom: '1px solid #f0f0f0', fontWeight: 600, fontFamily: '"DM Mono",monospace', whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[...result.all_candidates].sort((a, b) => b.score - a.score).map((eng, i) => {
                            const isWinner = eng.engineer_id === result.assigned_engineer?.engineer_id
                            return (
                              <tr key={eng.engineer_id} style={{ background: isWinner ? '#f0fdf4' : 'transparent', borderBottom: '1px solid #f7f7f7' }}>
                                <td style={{ padding: '10px 14px', fontFamily: '"DM Mono",monospace', color: '#aaa', fontSize: 11 }}>{i + 1}</td>
                                <td style={{ padding: '10px 14px' }}>
                                  <div style={{ fontWeight: isWinner ? 700 : 500 }}>{isWinner ? '★ ' : ''}{eng.name}</div>
                                  <div style={{ fontSize: 10, color: '#888', fontFamily: '"DM Mono",monospace' }}>{eng.engineer_id}</div>
                                </td>
                                <td style={{ padding: '10px 14px', color: '#555', fontSize: 11 }}>{eng.city}, {eng.country}</td>
                                <td style={{ padding: '10px 14px' }}>
                                  {eng.score_breakdown.domain_match > 0
                                    ? <span className="tag tag-green">✓ Match</span>
                                    : <span className="tag tag-gray">✗ None</span>}
                                </td>
                                <td style={{ padding: '10px 14px', fontFamily: '"DM Mono",monospace', fontWeight: 600 }}>
                                  <span style={{ color: eng.score_breakdown.tz_diff_hours === 0 ? '#16a34a' : eng.score_breakdown.tz_diff_hours <= 3 ? '#d97706' : '#dc2626' }}>
                                    {eng.score_breakdown.tz_diff_hours}h
                                  </span>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 36, height: 4, background: '#f0f0f0', borderRadius: 2, overflow: 'hidden' }}>
                                      <div style={{ height: '100%', width: `${Math.min((eng.active_tickets / eng.max_capacity) * 100, 100)}%`, background: '#d97706', borderRadius: 2 }} />
                                    </div>
                                    <span style={{ fontSize: 10, fontFamily: '"DM Mono",monospace', color: '#888' }}>{eng.active_tickets}/{eng.max_capacity}</span>
                                  </div>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  <span style={{ fontFamily: '"DM Mono",monospace', fontWeight: 700, fontSize: 14, color: scoreColor(eng.score) }}>{eng.score}</span>
                                </td>
                                <td style={{ padding: '10px 14px' }}>
                                  {isWinner
                                    ? <span className="tag tag-green">★ Assigned</span>
                                    : <span className="tag tag-gray">Skipped</span>}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}