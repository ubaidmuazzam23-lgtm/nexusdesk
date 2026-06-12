'use client'
// File: frontend/src/app/admin/tickets/page.tsx

import { useState, useEffect, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Ticket {
  id: string; ticket_number: string; title: string; domain: string
  priority: string; status: string; complexity: string
  engineer_name: string; engineer_id: string
  user_name: string; user_city: string; user_country: string; user_timezone: string
  created_at: string; resolved_at: string; sla_deadline: string; sla_breached: boolean
  ai_diagnosis: string; description: string; steps_tried: string; resolution_notes: string
  cnn_image_result: string
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',other:'Other',
}[d] || d)

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .tkt{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .tkt *{box-sizing:border-box}
  .tkt .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .tkt .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:10px;min-height:40px}
  .tkt .c-head h3{margin:0;font-size:12px;font-weight:600}
  .tkt .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .tkt .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .tkt .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .tkt .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .tkt .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .tkt .pill-pur{background:#f0edf8;color:#5b3d8a;border-color:transparent}
  .tkt table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .tkt table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .tkt table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .tkt table.dt tr{cursor:pointer}
  .tkt table.dt tr:hover td{background:#f9f9f9}
  .tkt table.dt tr.sel td{background:#e8f2ed}
  .tkt .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .tkt .btn:hover{background:#EBEBEB}
  .tkt .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .tkt .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .tkt .chip{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:12px;background:#EBEBEB;border:1px solid #CBCBCB;font-size:11px;color:#3a3a3a;cursor:pointer;font-weight:500;transition:all .1s}
  .tkt .chip:hover,.tkt .chip.on{background:#174D38;color:#fff;border-color:#174D38}
  .tkt .mono{font-family:"JetBrains Mono",monospace}
  .tkt .muted{color:#6b6b6b}
  .tkt .small{font-size:11px}
  .tkt .tiny{font-size:10px}
  .tkt .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .tkt .row{display:flex;align-items:center;gap:8px}
  .tkt .grow{flex:1}
  .tkt .kb-c{background:#EBEBEB;border:1px solid #CBCBCB;border-radius:4px;padding:8px 10px;font-size:12px;color:#3a3a3a;line-height:1.6}
  .tkt .sec-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-bottom:5px;display:block}
`

export default function TicketsPage() {
  const [tickets, setTickets]     = useState<Ticket[]>([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState<Ticket | null>(null)
  const [search, setSearch]       = useState('')
  const [prioFilter, setPrioFilter] = useState('All')
  const [statusFilter, setStatusFilter] = useState('All')

  const hdrs = useCallback(() => ({ Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}` }), [])

  useEffect(() => { fetchTickets() }, [])

  const fetchTickets = async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/admin/tickets`, { headers: hdrs() })
      if (r.ok) setTickets(await r.json())
    } catch {} finally { setLoading(false) }
  }

  const filtered = tickets.filter(t => {
    if (prioFilter !== 'All' && t.priority.toLowerCase() !== prioFilter.toLowerCase()) return false
    if (statusFilter !== 'All' && t.status !== statusFilter) return false
    if (search && !t.title.toLowerCase().includes(search.toLowerCase()) &&
        !t.ticket_number.toLowerCase().includes(search.toLowerCase()) &&
        !t.user_name?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const pPill = (p: string) => p === 'critical' ? 'pill-crit' : p === 'high' ? 'pill-warn' : p === 'medium' ? 'pill-grn' : ''
  const sPill = (s: string) => s === 'resolved' ? 'pill-ok' : s === 'in_progress' ? 'pill-pur' : s === 'open' ? 'pill-warn' : ''

  const fmtTime = (iso: string) => {
    try { return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
    catch { return iso }
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="tkt" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>

        {/* Header */}
        <div className="row">
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-.01em' }}>Global Tickets</div>
            <div className="small muted">{tickets.length} total · all engineers · all regions</div>
          </div>
          <span className="grow" />
          <button className="btn btn-sm" onClick={fetchTickets}>↻ Refresh</button>
        </div>

        {/* Filters */}
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <input placeholder="Search tickets, users..." value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 260, background: '#fff', height: 28, fontFamily: 'inherit', fontSize: 12, border: '1px solid #CBCBCB', borderRadius: 4, padding: '0 10px', outline: 'none' }} />
          <div style={{ display: 'flex', gap: 4 }}>
            {['All', 'Critical', 'High', 'Medium', 'Low'].map(p => (
              <span key={p} className={`chip ${prioFilter === p ? 'on' : ''}`} onClick={() => setPrioFilter(p)}>{p}</span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {['All', 'open', 'in_progress', 'resolved'].map(s => (
              <span key={s} className={`chip ${statusFilter === s ? 'on' : ''}`} onClick={() => setStatusFilter(s)}>{s.replace('_', ' ')}</span>
            ))}
          </div>
        </div>

        {/* Split layout */}
        <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 400px' : '1fr', gap: 12, flex: 1, overflow: 'hidden', minHeight: 0 }}>

          {/* Table */}
          <div className="card" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ overflow: 'auto', flex: 1 }}>
              <table className="dt">
                <thead>
                  <tr><th>ID</th><th>Priority</th><th>Issue</th><th>Domain</th><th>User</th><th>Engineer</th><th>Status</th><th>Created</th></tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={8} style={{ textAlign: 'center', padding: 32, color: '#6b6b6b' }}>Loading tickets...</td></tr>
                  ) : filtered.length === 0 ? (
                    <tr><td colSpan={8} style={{ textAlign: 'center', padding: 32, color: '#6b6b6b' }}>No tickets found</td></tr>
                  ) : filtered.map(t => (
                    <tr key={t.id} className={selected?.id === t.id ? 'sel' : ''} onClick={() => setSelected(selected?.id === t.id ? null : t)}>
                      <td><span className="mono" style={{ color: '#174D38', fontWeight: 600, fontSize: 11 }}>{t.ticket_number}</span></td>
                      <td><span className={`pill ${pPill(t.priority)}`}>{t.priority}</span></td>
                      <td style={{ maxWidth: 240 }}>
                        <div className="trunc" style={{ fontWeight: 500 }}>{t.title}</div>
                        {t.cnn_image_result && <span className="pill pill-pur" style={{ marginTop: 2 }}>📸</span>}
                        {t.sla_breached && <span className="pill pill-crit" style={{ marginTop: 2 }}>SLA</span>}
                      </td>
                      <td><span className="pill">{dLabel(t.domain)}</span></td>
                      <td className="small">
                        {t.user_name}
                        {t.user_city && <div className="tiny muted">{t.user_city}</div>}
                      </td>
                      <td className="small">{t.engineer_name || <span className="muted">Unassigned</span>}</td>
                      <td><span className={`pill ${sPill(t.status)}`}>{t.status.replace('_', ' ')}</span></td>
                      <td className="small muted mono">{fmtTime(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Detail panel */}
          {selected && (
            <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div className="c-head" style={{ background: '#174D38', borderRadius: '6px 6px 0 0', borderBottom: 'none', flexShrink: 0 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 10, color: 'rgba(255,255,255,.5)', fontFamily: '"JetBrains Mono",monospace', marginBottom: 3 }}>{selected.ticket_number}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', lineHeight: 1.3 }} className="trunc">{selected.title}</div>
                </div>
                <button className="btn btn-sm" style={{ background: 'rgba(255,255,255,.15)', border: 'none', color: '#fff', flexShrink: 0 }} onClick={() => setSelected(null)}>✕</button>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>

                {/* Badges */}
                <div className="row" style={{ flexWrap: 'wrap', gap: 5 }}>
                  <span className={`pill ${pPill(selected.priority)}`}>{selected.priority}</span>
                  <span className={`pill ${sPill(selected.status)}`}>{selected.status.replace('_', ' ')}</span>
                  <span className="pill">{dLabel(selected.domain)}</span>
                  {selected.sla_breached && <span className="pill pill-crit">SLA Breach</span>}
                </div>

                {/* User */}
                <div className="card">
                  <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>User</span></div>
                  <div style={{ padding: '8px 12px', fontSize: 12 }}>
                    <div style={{ fontWeight: 600 }}>{selected.user_name}</div>
                    {selected.user_city && <div className="muted small">{selected.user_city}, {selected.user_country}</div>}
                    <div className="tiny muted" style={{ marginTop: 4 }}>
                      Created {fmtTime(selected.created_at)}
                    </div>
                  </div>
                </div>

                {/* Engineer */}
                {selected.engineer_name && (
                  <div className="card">
                    <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>Assigned Engineer</span></div>
                    <div style={{ padding: '8px 12px', fontSize: 12 }}>
                      <div style={{ fontWeight: 600 }}>{selected.engineer_name}</div>
                      <div className="tiny muted mono">{selected.engineer_id}</div>
                    </div>
                  </div>
                )}

                {/* Description */}
                {selected.description && (
                  <div>
                    <span className="sec-lbl">Description</span>
                    <div className="kb-c">{selected.description}</div>
                  </div>
                )}

                {/* AI Diagnosis */}
                {selected.ai_diagnosis && (
                  <div>
                    <span className="sec-lbl" style={{ color: '#174D38' }}>AI Diagnosis</span>
                    <div className="kb-c" style={{ borderLeft: '3px solid #174D38' }}>{selected.ai_diagnosis}</div>
                  </div>
                )}

                {/* Resolution */}
                {selected.resolution_notes && (
                  <div>
                    <span className="sec-lbl" style={{ color: '#1a7a4a' }}>Resolution Notes</span>
                    <div className="kb-c" style={{ borderLeft: '3px solid #1a7a4a' }}>{selected.resolution_notes}</div>
                  </div>
                )}

                {/* Resolved at */}
                {selected.resolved_at && (
                  <div className="tiny muted mono">Resolved {fmtTime(selected.resolved_at)}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}