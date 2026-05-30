// Location: ./frontend/src/app/manager/tickets/page.tsx
'use client'

import { useState, useEffect, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Ticket {
  id: string; ticket_number: string; title: string; description: string
  domain: string; priority: string; status: string; complexity: string
  user_name: string; user_email: string; user_city: string; user_timezone: string
  engineer_name: string; engineer_id: string
  sla_deadline: string; sla_breached: boolean
  created_at: string; resolved_at: string
}

interface Member {
  engineer_id: string; full_name: string
  availability_status: string; active_ticket_count: number
  domain_expertise: string[]
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',other:'Other',
}[d] || d)

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .mq *{box-sizing:border-box}
  .mq{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .mq .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .mq .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px}
  .mq .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .mq .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .mq .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .mq .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .mq .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .mq .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .mq .pill-blue{background:#e8f0fd;color:#1a56b0;border-color:transparent}
  .mq .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
  .mq .dot-ok{background:#1a7a4a}.mq .dot-warn{background:#8a5a00}.mq .dot-crit{background:#4D1717}
  .mq table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .mq table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .mq table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .mq table.dt tr{cursor:pointer}
  .mq table.dt tr:hover td{background:#f9f9f9}
  .mq table.dt tr.sel td{background:#e8f2ed}
  .mq .mono{font-family:"JetBrains Mono",monospace}
  .mq .muted{color:#6b6b6b}.mq .small{font-size:11px}.mq .tiny{font-size:10px}
  .mq .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mq .row{display:flex;align-items:center;gap:8px}
  .mq .grow{flex:1}
  .mq .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .mq .btn:hover{background:#EBEBEB}
  .mq .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .mq .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .mq select,.mq input{height:28px;padding:0 8px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;font-family:inherit;font-size:12px;color:#141414;cursor:pointer}
  .mq select:focus,.mq input:focus{outline:none;border-color:#174D38}
  .mq .sec-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace}
  .mq .kb-c{background:#EBEBEB;border:1px solid #CBCBCB;border-radius:4px;padding:8px 10px;font-size:12px;color:#3a3a3a;line-height:1.5}
`

export default function ManagerTicketsPage() {
  const [tickets,      setTickets]      = useState<Ticket[]>([])
  const [members,      setMembers]      = useState<Member[]>([])
  const [loading,      setLoading]      = useState(true)
  const [selected,     setSelected]     = useState<Ticket | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [assignTo,     setAssignTo]     = useState('')
  const [assigning,    setAssigning]    = useState(false)
  const [success,      setSuccess]      = useState('')
  const [error,        setError]        = useState('')

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    'Content-Type': 'application/json',
  }), [])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const url = statusFilter
        ? `${API}/api/v1/manager/tickets?status=${statusFilter}`
        : `${API}/api/v1/manager/tickets`
      const [tR, mR] = await Promise.all([
        fetch(url, { headers: hdrs() }),
        fetch(`${API}/api/v1/manager/my-team`, { headers: hdrs() }),
      ])
      if (tR.ok) setTickets(await tR.json())
      if (mR.ok) { const d = await mR.json(); setMembers(d.members || []) }
    } catch { }
    finally { setLoading(false) }
  }, [hdrs, statusFilter])

  useEffect(() => { fetchAll() }, [fetchAll])

  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(''), 3000); return () => clearTimeout(t) }
  }, [success])

  const assignTicket = async () => {
    if (!selected || !assignTo) return
    setAssigning(true)
    setError('')
    try {
      const r = await fetch(`${API}/api/v1/manager/tickets/${selected.id}/assign`, {
        method: 'PATCH', headers: hdrs(), body: JSON.stringify({ engineer_id: assignTo }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail)
      setSuccess(`Ticket assigned to ${assignTo}`)
      setAssignTo('')
      fetchAll()
      setSelected(null)
    } catch (err: any) { setError(err.message) }
    finally { setAssigning(false) }
  }

  const fmtTime = (s: string) => s
    ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'

  const pPill = (p: string) => p === 'critical' ? 'pill-crit' : p === 'high' ? 'pill-warn' : p === 'medium' ? 'pill-grn' : ''
  const sPill = (s: string) => s === 'resolved' ? 'pill-ok' : s === 'in_progress' ? 'pill-blue' : s === 'open' ? 'pill-warn' : ''

  const openCount     = tickets.filter(t => t.status === 'open').length
  const inProgCount   = tickets.filter(t => t.status === 'in_progress').length
  const breachedCount = tickets.filter(t => t.sla_breached).length

  return (
    <>
      <style>{CSS}</style>
      <div className="mq" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>Ticket Queue</div>
            <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
              {openCount} open · {inProgCount} in progress · {breachedCount > 0 ? `${breachedCount} SLA breached` : 'all within SLA'}
            </div>
          </div>
          <div className="row">
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ fontFamily: '"JetBrains Mono",monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: '.04em' }}>
              <option value="">All Status</option>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
            <button className="btn btn-sm btn-p" onClick={fetchAll}>↻ Refresh</button>
          </div>
        </div>

        {/* Banners */}
        {success && <div style={{ padding: '10px 14px', background: '#e6f4ed', border: '1px solid #b7dfc8', borderRadius: 4, fontSize: 13, color: '#1a7a4a' }}>✓ {success}</div>}
        {error   && <div style={{ padding: '10px 14px', background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 13, color: '#4D1717' }}>✕ {error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap: 12 }}>

          {/* Table */}
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              <h3>All Tickets</h3>
              <span className="grow"/>
              {breachedCount > 0 && <span className="pill pill-crit">{breachedCount} SLA BREACH</span>}
              <span className="small muted">{tickets.length} tickets</span>
            </div>
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>Loading...</div>
            ) : tickets.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No tickets found.</div>
            ) : (
              <table className="dt">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Title</th>
                    <th>Domain</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Assigned To</th>
                    <th>SLA</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {tickets.map(t => (
                    <tr
                      key={t.id}
                      className={selected?.id === t.id ? 'sel' : ''}
                      onClick={() => setSelected(selected?.id === t.id ? null : t)}
                    >
                      <td><span className="mono tiny" style={{ color: '#174D38', fontWeight: 600 }}>{t.ticket_number}</span></td>
                      <td>
                        <div style={{ fontWeight: 500, maxWidth: 180 }} className="trunc">{t.title}</div>
                        <div className="tiny muted">{t.user_name}</div>
                      </td>
                      <td><span className="pill" style={{ fontSize: 9 }}>{dLabel(t.domain)}</span></td>
                      <td><span className={`pill ${pPill(t.priority)}`}>{t.priority}</span></td>
                      <td><span className={`pill ${sPill(t.status)}`}>{t.status.replace('_', ' ')}</span></td>
                      <td>{t.engineer_name
                        ? <span className="small">{t.engineer_name}</span>
                        : <span className="small muted">Unassigned</span>}
                      </td>
                      <td>
                        {t.sla_breached
                          ? <span className="pill pill-crit">Breached</span>
                          : <span className="tiny muted mono">{fmtTime(t.sla_deadline)}</span>}
                      </td>
                      <td><span className="tiny muted mono">{fmtTime(t.created_at)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Detail + assign panel */}
          {selected && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
              <div className="c-head">
                <h3>{selected.ticket_number}</h3>
                <span className="grow"/>
                <button className="btn btn-sm" onClick={() => setSelected(null)}>✕</button>
              </div>

              <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 12, flex: 1, overflowY: 'auto' }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{selected.title}</div>

                <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                  <span className={`pill ${pPill(selected.priority)}`}>{selected.priority}</span>
                  <span className={`pill ${sPill(selected.status)}`}>{selected.status.replace('_', ' ')}</span>
                  {selected.sla_breached && <span className="pill pill-crit">SLA Breached</span>}
                  {selected.complexity && <span className="pill">{selected.complexity}</span>}
                </div>

                <div className="kb-c" style={{ fontSize: 12, lineHeight: 1.6 }}>{selected.description}</div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {[
                    { l: 'User',       v: selected.user_name,                     sub: selected.user_city },
                    { l: 'Domain',     v: dLabel(selected.domain),                 sub: '' },
                    { l: 'Assigned',   v: selected.engineer_name || 'Unassigned', sub: selected.engineer_id },
                    { l: 'Created',    v: fmtTime(selected.created_at),            sub: '' },
                  ].map((s, i) => (
                    <div key={i}>
                      <div className="sec-lbl">{s.l}</div>
                      <div className="small" style={{ marginTop: 2 }}>{s.v || '—'}</div>
                      {s.sub && <div className="tiny muted">{s.sub}</div>}
                    </div>
                  ))}
                </div>

                {/* Assign section */}
                <div style={{ padding: '12px', background: '#e8f2ed', border: '1px solid #b7dfc8', borderRadius: 4 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: '#174D38', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.06em', fontFamily: '"JetBrains Mono",monospace' }}>
                    Assign to Engineer
                  </div>
                  <select
                    value={assignTo}
                    onChange={e => setAssignTo(e.target.value)}
                    style={{ width: '100%', height: 32, marginBottom: 8, fontSize: 12 }}
                  >
                    <option value="">— Select engineer —</option>
                    {members.filter(m => m.availability_status === 'available').map(m => (
                      <option key={m.engineer_id} value={m.engineer_id}>
                        {m.full_name} ({m.engineer_id}) · {m.active_ticket_count} active
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn btn-p"
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={assignTicket}
                    disabled={!assignTo || assigning}
                  >
                    {assigning ? 'Assigning...' : 'Assign Ticket →'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}