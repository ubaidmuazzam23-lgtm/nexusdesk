// Location: ./frontend/src/app/manager/team/page.tsx
'use client'

import { useState, useEffect, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Member {
  id: string; user_id: string; full_name: string; email: string
  engineer_id: string; role_in_team: string; domain_expertise: string[]
  availability_status: string; active_ticket_count: number
  total_resolved: number; sla_compliance_rate: number; joined_at: string
}

interface Team {
  team_id: string; name: string; description: string
  domain_focus: string[]; region: string; timezone: string
  member_count: number; members: Member[]
  active_ticket_count: number; max_ticket_capacity: number
  total_resolved: number; sla_compliance_rate: number
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',
}[d] || d)

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .mt *{box-sizing:border-box}
  .mt{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .mt .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .mt .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px}
  .mt .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .mt .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .mt .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .mt .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .mt .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .mt .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .mt .pill-pur{background:#f0edf8;color:#5b3d8a;border-color:transparent}
  .mt .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
  .mt .dot-ok{background:#1a7a4a}.mt .dot-warn{background:#8a5a00}.mt .dot-crit{background:#4D1717}
  .mt table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .mt table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .mt table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .mt table.dt tr:hover td{background:#f9f9f9}
  .mt .bar{height:5px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
  .mt .bar-f{height:100%;transition:width .4s;border-radius:3px}
  .mt .mono{font-family:"JetBrains Mono",monospace}
  .mt .muted{color:#6b6b6b}.mt .small{font-size:11px}.mt .tiny{font-size:10px}
  .mt .row{display:flex;align-items:center;gap:8px}
  .mt .grow{flex:1}
  .mt .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .mt .btn:hover{background:#EBEBEB}
  .mt .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .mt .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .mt select{height:26px;padding:0 8px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;font-family:"JetBrains Mono",monospace;font-size:11px;color:#141414;cursor:pointer}
  .mt select:focus{outline:none;border-color:#174D38}
  .mt .stat-lbl{font-size:10px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.08em;font-family:"JetBrains Mono",monospace;font-weight:600}
  .mt .stat-v{font-size:22px;font-weight:700;letter-spacing:-.02em;font-family:"JetBrains Mono",monospace}
`

export default function ManagerTeamPage() {
  const [team,     setTeam]     = useState<Team | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)
  const [success,  setSuccess]  = useState('')
  const [error,    setError]    = useState('')

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    'Content-Type': 'application/json',
  }), [])

  const fetchTeam = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/manager/my-team`, { headers: hdrs() })
      if (r.ok) setTeam(await r.json())
    } catch { }
    finally { setLoading(false) }
  }, [hdrs])

  useEffect(() => { fetchTeam() }, [fetchTeam])

  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(''), 3000); return () => clearTimeout(t) }
  }, [success])

  const updateAvailability = async (engineerId: string, status: string) => {
    setUpdating(engineerId)
    try {
      const r = await fetch(`${API}/api/v1/manager/members/${engineerId}/availability`, {
        method: 'PATCH', headers: hdrs(), body: JSON.stringify({ status }),
      })
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail) }
      setSuccess('Availability updated')
      fetchTeam()
    } catch (err: any) { setError(err.message) }
    finally { setUpdating(null) }
  }

  if (loading) return (
    <>
      <style>{CSS}</style>
      <div className="mt" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>Loading...</div>
    </>
  )

  if (!team) return (
    <>
      <style>{CSS}</style>
      <div className="mt" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No team assigned.</div>
    </>
  )

  return (
    <>
      <style>{CSS}</style>
      <div className="mt" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>{team.name}</div>
            <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
              {team.team_id} · {team.region} · {team.timezone}
            </div>
          </div>
          <button className="btn btn-sm btn-p" onClick={fetchTeam}>↻ Refresh</button>
        </div>

        {/* Banners */}
        {success && <div style={{ padding: '10px 14px', background: '#e6f4ed', border: '1px solid #b7dfc8', borderRadius: 4, fontSize: 13, color: '#1a7a4a' }}>✓ {success}</div>}
        {error   && <div style={{ padding: '10px 14px', background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 13, color: '#4D1717' }}>✕ {error}</div>}

        {/* Team stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          {[
            { l: 'Members',       v: team.member_count,       accent: '#174D38' },
            { l: 'Active Tickets',v: team.active_ticket_count, accent: team.active_ticket_count > team.max_ticket_capacity * 0.8 ? '#4D1717' : '#8a5a00' },
            { l: 'Total Resolved',v: team.total_resolved,      accent: '#1a7a4a' },
            { l: 'SLA Compliance',v: `${team.sla_compliance_rate}%`, accent: team.sla_compliance_rate >= 90 ? '#1a7a4a' : '#4D1717' },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: '14px 16px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: s.accent }} />
              <div className="stat-lbl">{s.l}</div>
              <div className="stat-v" style={{ color: s.accent, marginTop: 5 }}>{s.v}</div>
            </div>
          ))}
        </div>

        {/* Domain focus */}
        {team.domain_focus.length > 0 && (
          <div className="card" style={{ padding: '12px 14px' }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.08em', color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginBottom: 8 }}>Team Domain Focus</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {team.domain_focus.map(d => (
                <span key={d} className="pill pill-grn">{dLabel(d)}</span>
              ))}
            </div>
          </div>
        )}

        {/* Members table */}
        <div className="card">
          <div className="c-head">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
            <h3>Team Members</h3>
            <span className="grow"/>
            <span className="small muted">{team.member_count} engineers · cross-domain</span>
          </div>
          {team.members.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No members yet.</div>
          ) : (
            <table className="dt">
              <thead>
                <tr>
                  <th>Engineer</th>
                  <th>Domains</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Active Tickets</th>
                  <th>Resolved</th>
                  <th>SLA</th>
                  <th>Set Availability</th>
                </tr>
              </thead>
              <tbody>
                {team.members.map(m => (
                  <tr key={m.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 22, height: 22, borderRadius: 3, background: '#174D38', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 9, fontWeight: 700, flexShrink: 0 }}>
                          {m.full_name.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 500 }}>{m.full_name}</div>
                          <div className="tiny muted mono">{m.engineer_id}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                        {m.domain_expertise.slice(0, 2).map(d => (
                          <span key={d} className="pill" style={{ fontSize: 9 }}>{dLabel(d)}</span>
                        ))}
                        {m.domain_expertise.length > 2 && <span className="pill" style={{ fontSize: 9 }}>+{m.domain_expertise.length - 2}</span>}
                      </div>
                    </td>
                    <td><span className={`pill ${m.role_in_team === 'lead' ? 'pill-pur' : ''}`}>{m.role_in_team}</span></td>
                    <td>
                      <div className="row" style={{ gap: 5 }}>
                        <span className={`dot ${m.availability_status === 'available' ? 'dot-ok' : m.availability_status === 'busy' ? 'dot-warn' : 'dot-crit'}`}/>
                        <span className="small">{m.availability_status}</span>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 48 }} className="bar">
                          <div className="bar-f" style={{ width: `${Math.min((m.active_ticket_count / 10) * 100, 100)}%`, background: m.active_ticket_count > 7 ? '#4D1717' : '#174D38' }}/>
                        </div>
                        <span className="tiny mono muted">{m.active_ticket_count}</span>
                      </div>
                    </td>
                    <td className="mono small" style={{ color: '#1a7a4a' }}>{m.total_resolved}</td>
                    <td className="small" style={{ color: m.sla_compliance_rate >= 90 ? '#1a7a4a' : '#4D1717' }}>{m.sla_compliance_rate}%</td>
                    <td>
                      <select
                        value={m.availability_status}
                        disabled={updating === m.engineer_id}
                        onChange={e => updateAvailability(m.engineer_id, e.target.value)}
                      >
                        <option value="available">Available</option>
                        <option value="busy">Busy</option>
                        <option value="away">Away</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}