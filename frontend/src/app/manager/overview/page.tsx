// Location: ./frontend/src/app/manager/overview/page.tsx
'use client'

import { useState, useEffect, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Overview {
  team_name: string; team_id: string
  total_members: number; available_members: number
  busy_members: number; away_members: number
  total_tickets: number; open_tickets: number
  resolved_tickets: number; sla_breached: number
  sla_compliance_rate: number; avg_resolution_time: number
}

interface Member {
  full_name: string; engineer_id: string
  availability_status: string; active_ticket_count: number
  total_resolved: number; domain_expertise: string[]
}

interface Ticket {
  id: string; ticket_number: string; title: string
  domain: string; priority: string; status: string
  user_name: string; user_city: string
  engineer_name: string; sla_breached: boolean
  created_at: string
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',other:'Other',
}[d] || d)

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .mg *{box-sizing:border-box}
  .mg{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .mg .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .mg .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px}
  .mg .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .mg .stat-lbl{font-size:10px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.08em;font-family:"JetBrains Mono",monospace;font-weight:600}
  .mg .stat-v{font-size:26px;font-weight:700;letter-spacing:-.02em;line-height:1.1;margin-top:5px;font-feature-settings:"tnum";font-family:"JetBrains Mono",monospace}
  .mg .stat-d{font-size:11px;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-top:3px}
  .mg .stat-d.up{color:#1a7a4a}.mg .stat-d.dn{color:#4D1717}
  .mg .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .mg .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .mg .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .mg .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .mg .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .mg .pill-blue{background:#e8f0fd;color:#1a56b0;border-color:transparent}
  .mg .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
  .mg .dot-ok{background:#1a7a4a}.mg .dot-warn{background:#8a5a00}.mg .dot-crit{background:#4D1717}
  .mg .pulse{animation:mg-pulse 1.8s ease-in-out infinite}
  @keyframes mg-pulse{0%,100%{opacity:1}50%{opacity:.3}}
  .mg table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .mg table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .mg table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .mg table.dt tr:hover td{background:#f9f9f9;cursor:pointer}
  .mg .bar{height:5px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
  .mg .bar-f{height:100%;transition:width .4s;border-radius:3px}
  .mg .mono{font-family:"JetBrains Mono",monospace}
  .mg .muted{color:#6b6b6b}.mg .small{font-size:11px}.mg .tiny{font-size:10px}
  .mg .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mg .row{display:flex;align-items:center;gap:8px}
  .mg .grow{flex:1}
  .mg .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .mg .btn:hover{background:#EBEBEB}
  .mg .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .mg .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .mg .sec-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace}
`

export default function ManagerOverviewPage() {
  const [overview, setOverview]   = useState<Overview | null>(null)
  const [members,  setMembers]    = useState<Member[]>([])
  const [tickets,  setTickets]    = useState<Ticket[]>([])
  const [loading,  setLoading]    = useState(true)
  const [lastUpdated, setLastUpdated] = useState(new Date())

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  }), [])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [oR, tR, mR] = await Promise.all([
        fetch(`${API}/api/v1/manager/overview`,  { headers: hdrs() }),
        fetch(`${API}/api/v1/manager/tickets`,   { headers: hdrs() }),
        fetch(`${API}/api/v1/manager/my-team`,   { headers: hdrs() }),
      ])
      if (oR.ok) setOverview(await oR.json())
      if (tR.ok) setTickets(await tR.json())
      if (mR.ok) { const d = await mR.json(); setMembers(d.members || []) }
      setLastUpdated(new Date())
    } catch { }
    finally { setLoading(false) }
  }, [hdrs])

  useEffect(() => { fetchAll() }, [fetchAll])

  if (loading || !overview) return (
    <>
      <style>{CSS}</style>
      <div className="mg" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>
        {loading ? 'Loading...' : 'No team assigned. Contact your admin.'}
      </div>
    </>
  )

  const openTickets  = tickets.filter(t => t.status === 'open' || t.status === 'in_progress')
  const breachedTkts = tickets.filter(t => t.sla_breached)

  const kpis = [
    { l: 'Open Tickets',    v: overview.open_tickets,        d: `${overview.total_tickets} total`,               du: overview.open_tickets > 10 ? 'dn' : '', accent: '#174D38' },
    { l: 'Resolved',        v: overview.resolved_tickets,    d: 'all time',                                       du: 'up',                                     accent: '#1a7a4a' },
    { l: 'SLA Compliance',  v: `${overview.sla_compliance_rate}%`, d: `${overview.sla_breached} breached`,        du: overview.sla_compliance_rate >= 90 ? 'up' : 'dn', accent: overview.sla_compliance_rate >= 90 ? '#1a7a4a' : '#4D1717' },
    { l: 'Avg Resolution',  v: `${overview.avg_resolution_time}m`, d: 'per ticket',                              du: '',                                       accent: '#141414' },
    { l: 'Team Size',       v: overview.total_members,       d: `${overview.available_members} available`,        du: 'up',                                     accent: '#174D38' },
  ]

  return (
    <>
      <style>{CSS}</style>
      <div className="mg" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>{overview.team_name}</div>
            <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
              {overview.team_id} · Last updated {lastUpdated.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </div>
          </div>
          <div className="row">
            <span className="dot dot-ok pulse"/>
            <span className="small muted">Live</span>
            <button className="btn btn-sm btn-p" onClick={fetchAll} disabled={loading}>↻ Refresh</button>
          </div>
        </div>

        {/* KPI cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
          {kpis.map((k, i) => (
            <div key={i} className="card" style={{ padding: '14px 16px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: k.accent }} />
              <div className="stat-lbl">{k.l}</div>
              <div className="stat-v" style={{ color: k.accent }}>{k.v}</div>
              <div className={`stat-d ${k.du}`}>{k.d}</div>
            </div>
          ))}
        </div>

        {/* Availability + Quick actions */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

          {/* Availability */}
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
              <h3>Team Availability</h3>
              <span className="grow"/>
              <span className="small muted mono">{overview.total_members} total</span>
            </div>
            <div style={{ padding: '12px 14px', display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
              {[
                { label: 'Available', count: overview.available_members, dotClass: 'dot-ok',   color: '#1a7a4a' },
                { label: 'Busy',      count: overview.busy_members,      dotClass: 'dot-warn', color: '#8a5a00' },
                { label: 'Away',      count: overview.away_members,      dotClass: 'dot-crit', color: '#4D1717' },
              ].map((s, i) => (
                <div key={i} style={{ textAlign: 'center', padding: '12px 8px', background: '#FAFAFA', borderRadius: 4, border: '1px solid #EBEBEB' }}>
                  <div className="row" style={{ justifyContent: 'center', marginBottom: 6 }}>
                    <span className={`dot ${s.dotClass}`}/>
                    <span className="small" style={{ color: '#6b6b6b' }}>{s.label}</span>
                  </div>
                  <div className="stat-v" style={{ fontSize: 22, color: s.color }}>{s.count}</div>
                </div>
              ))}
            </div>

            {/* Mini capacity bars */}
            <div style={{ padding: '0 14px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {members.slice(0, 5).map(m => (
                <div key={m.engineer_id} className="row">
                  <div style={{ width: 90, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11 }}>{m.full_name}</div>
                  <div style={{ flex: 1 }} className="bar">
                    <div className="bar-f" style={{
                      width: `${Math.min((m.active_ticket_count / 10) * 100, 100)}%`,
                      background: m.active_ticket_count > 7 ? '#4D1717' : m.active_ticket_count > 4 ? '#8a5a00' : '#174D38',
                    }}/>
                  </div>
                  <span className="tiny mono muted">{m.active_ticket_count}</span>
                  <span className={`dot ${m.availability_status === 'available' ? 'dot-ok' : m.availability_status === 'busy' ? 'dot-warn' : 'dot-crit'}`}/>
                </div>
              ))}
            </div>
          </div>

          {/* Recent tickets */}
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              <h3>Recent Tickets</h3>
              <span className="grow"/>
              {breachedTkts.length > 0 && <span className="pill pill-crit">{breachedTkts.length} SLA BREACH</span>}
              <a href="/manager/tickets" style={{ fontSize: 11, color: '#174D38', textDecoration: 'none', fontWeight: 500 }}>View all →</a>
            </div>
            <div style={{ overflowY: 'auto', maxHeight: 220 }}>
              {openTickets.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center', color: '#6b6b6b', fontSize: 12 }}>
                  <span className="dot dot-ok" style={{ marginRight: 6 }}/>No open tickets
                </div>
              ) : openTickets.slice(0, 8).map(t => (
                <div key={t.id} style={{ padding: '8px 14px', borderBottom: '1px solid #f0f0f0', display: 'grid', gridTemplateColumns: '76px 1fr auto', gap: 8, alignItems: 'center' }}>
                  <span className="tiny muted mono">{t.ticket_number}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</div>
                    <div className="tiny muted">{t.user_name} · {t.user_city || dLabel(t.domain)}</div>
                  </div>
                  <span className={`pill ${t.priority === 'critical' ? 'pill-crit' : t.priority === 'high' ? 'pill-warn' : t.priority === 'medium' ? 'pill-grn' : ''}`}>
                    {t.priority}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quick nav cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
          {[
            { label: 'Manage Team Members', sub: `${overview.total_members} engineers · ${overview.available_members} available`, href: '/manager/team', accent: '#174D38' },
            { label: 'Ticket Queue',        sub: `${overview.open_tickets} open · ${overview.sla_breached} SLA breached`,        href: '/manager/tickets', accent: overview.sla_breached > 0 ? '#4D1717' : '#174D38' },
            { label: 'Team Chat',           sub: 'Real-time group chat with your team',                                           href: '/manager/chat', accent: '#174D38' },
          ].map((a, i) => (
            <a key={i} href={a.href} style={{ display: 'block', textDecoration: 'none' }}>
              <div className="card" style={{ padding: '16px', cursor: 'pointer', transition: 'box-shadow .15s', position: 'relative', overflow: 'hidden' }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(0,0,0,.1)'}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.boxShadow = '0 1px 3px rgba(0,0,0,.07)'}
              >
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: a.accent }} />
                <div style={{ fontSize: 13, fontWeight: 600, color: '#141414', marginBottom: 4 }}>{a.label} →</div>
                <div className="small muted">{a.sub}</div>
              </div>
            </a>
          ))}
        </div>

        {/* Member table */}
        <div className="card">
          <div className="c-head">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
            <h3>Team Members</h3>
            <span className="grow"/>
            <a href="/manager/team" style={{ fontSize: 11, color: '#174D38', textDecoration: 'none', fontWeight: 500 }}>Manage →</a>
          </div>
          <table className="dt">
            <thead>
              <tr>
                <th>Engineer</th>
                <th>Domains</th>
                <th>Status</th>
                <th>Load</th>
                <th>Resolved</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m, i) => (
                <tr key={i}>
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
                  <td className="mono small">{m.total_resolved || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </div>
    </>
  )
}