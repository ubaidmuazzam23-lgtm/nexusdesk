'use client'
// File: frontend/src/app/admin/engineers/page.tsx

import { useState, useEffect, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Engineer {
  id: string; engineer_id: string; full_name: string; email: string
  domain_expertise: string[]; region: string; timezone: string; city: string; country: string
  seniority_level: string; max_ticket_capacity: number; availability_status: string
  active_ticket_count: number; is_activated: boolean; is_active: boolean
  total_resolved: number; sla_compliance_rate: number
}

const DOMAINS = [
  {v:'networking',l:'Networking'},{v:'hardware',l:'Hardware'},{v:'software',l:'Software'},
  {v:'security',l:'Security'},{v:'email_communication',l:'Email & Comm'},{v:'identity_access',l:'Identity & Access'},
  {v:'database',l:'Database'},{v:'cloud',l:'Cloud'},{v:'infrastructure',l:'Infrastructure'},
  {v:'devops',l:'DevOps'},{v:'erp_business_apps',l:'ERP & Business'},{v:'endpoint_management',l:'Endpoint Mgmt'},
]
const REGIONS = ['India','Europe','US','Asia Pacific','Middle East','Africa']
const SENIORITY = ['junior','mid','senior','lead']

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .adm{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .adm *{box-sizing:border-box}
  .adm .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .adm .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:10px;min-height:40px}
  .adm .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .adm .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .adm .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .adm .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .adm .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
  .adm .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .adm .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
  .adm .dot-ok{background:#1a7a4a}.adm .dot-warn{background:#8a5a00}.adm .dot-crit{background:#4D1717}
  .adm table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .adm table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .adm table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .adm table.dt tr:hover td{background:#f9f9f9}
  .adm .bar{height:5px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
  .adm .bar-f{height:100%;transition:width .4s;border-radius:3px}
  .adm .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .adm .btn:hover{background:#EBEBEB}
  .adm .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .adm .btn-p:hover{background:#1f6a4d!important}
  .adm .btn-r{background:#4D1717!important;color:#fff!important;border-color:#4D1717!important}
  .adm .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .adm .btn-g{background:transparent!important;border-color:transparent!important;color:#6b6b6b!important}
  .adm .chip{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:12px;background:#EBEBEB;border:1px solid #CBCBCB;font-size:11px;color:#3a3a3a;cursor:pointer;font-weight:500;transition:all .1s}
  .adm .chip:hover,.adm .chip.on{background:#174D38;color:#fff;border-color:#174D38}
  .adm .mono{font-family:"JetBrains Mono",monospace}
  .adm .muted{color:#6b6b6b}
  .adm .small{font-size:11px}
  .adm .tiny{font-size:10px}
  .adm .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .adm .row{display:flex;align-items:center;gap:8px}
  .adm .grow{flex:1}
  .adm input,.adm select,.adm textarea{font-family:inherit;font-size:12px;background:#EBEBEB;border:1px solid #CBCBCB;color:#141414;border-radius:4px;padding:6px 10px;width:100%;outline:none;transition:border-color .15s}
  .adm input:focus,.adm select:focus,.adm textarea:focus{border-color:#174D38;background:#fff}
  .adm textarea{resize:vertical;line-height:1.5}
  .adm .lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-bottom:5px;display:block}
`

export default function EngineersPage() {
  const [engineers, setEngineers] = useState<Engineer[]>([])
  const [loading, setLoading]     = useState(true)
  const [search, setSearch]       = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [showModal, setShowModal] = useState(false)
  const [creating, setCreating]   = useState(false)
  const [success, setSuccess]     = useState('')
  const [error, setError]         = useState('')
  const [form, setForm]           = useState({
    full_name: '', email: '', domain_expertise: [] as string[],
    region: 'India', timezone: 'Asia/Kolkata', seniority_level: 'mid', max_ticket_capacity: 10,
  })

  const hdrs = useCallback(() => ({ Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}` }), [])

  useEffect(() => { fetchEngineers() }, [search, statusFilter])

  const fetchEngineers = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      if (statusFilter !== 'all') params.set('status', statusFilter)
      const r = await fetch(`${API}/api/v1/admin/engineers?${params}`, { headers: hdrs() })
      if (r.ok) setEngineers(await r.json())
    } catch {} finally { setLoading(false) }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.domain_expertise.length) { setError('Select at least one domain'); return }
    setCreating(true); setError('')
    try {
      const r = await fetch(`${API}/api/v1/admin/engineers`, {
        method: 'POST', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Failed')
      setSuccess(`Engineer ${d.engineer_id} created — activation email sent.`)
      setShowModal(false)
      setForm({ full_name: '', email: '', domain_expertise: [], region: 'India', timezone: 'Asia/Kolkata', seniority_level: 'mid', max_ticket_capacity: 10 })
      fetchEngineers()
    } catch (err: any) { setError(err.message) }
    finally { setCreating(false) }
  }

  const handleDeactivate = async (engId: string) => {
    if (!confirm(`Deactivate ${engId}?`)) return
    const r = await fetch(`${API}/api/v1/admin/engineers/${engId}`, { method: 'DELETE', headers: hdrs() })
    if (r.ok) { setSuccess(`${engId} deactivated.`); fetchEngineers() }
  }

  const handleReactivate = async (engId: string) => {
    if (!confirm(`Reactivate ${engId}?`)) return
    const r = await fetch(`${API}/api/v1/admin/engineers/${engId}/reactivate`, { method: 'POST', headers: hdrs() })
    if (r.ok) { setSuccess(`${engId} reactivated.`); fetchEngineers() }
  }

  const toggleDomain = (v: string) => setForm(f => ({
    ...f, domain_expertise: f.domain_expertise.includes(v)
      ? f.domain_expertise.filter(x => x !== v)
      : [...f.domain_expertise, v],
  }))

  const getStatus = (e: Engineer) => {
    if (!e.is_active) return { l: 'Deactivated', c: 'dot-crit', p: 'pill-crit' }
    if (!e.is_activated) return { l: 'Pending', c: 'dot-warn', p: 'pill-warn' }
    if (e.availability_status === 'available') return { l: 'Available', c: 'dot-ok', p: 'pill-ok' }
    if (e.availability_status === 'busy') return { l: 'Busy', c: 'dot-warn', p: 'pill-warn' }
    return { l: 'Away', c: '', p: '' }
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="adm" style={{ padding: 16 }}>

        {/* Header */}
        <div className="row" style={{ marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-.01em' }}>Engineer Management</div>
            <div className="small muted">{engineers.length} engineers · all regions</div>
          </div>
          <span className="grow" />
          <button className="btn btn-p btn-sm" onClick={() => { setShowModal(true); setError('') }}>
            + Add Engineer
          </button>
        </div>

        {success && (
          <div style={{ padding: '10px 14px', background: '#e6f4ed', border: '1px solid #1a7a4a', borderRadius: 4, color: '#1a7a4a', fontSize: 12, marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
            {success}<button onClick={() => setSuccess('')} style={{ background: 'none', border: 'none', color: '#1a7a4a', cursor: 'pointer', fontSize: 14 }}>×</button>
          </div>
        )}

        {/* Filters */}
        <div className="row" style={{ marginBottom: 12, gap: 8 }}>
          <input placeholder="Search by name, email, ID, region..." value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 320, background: '#fff' }} />
          <div style={{ display: 'flex', gap: 4 }}>
            {[{ v: 'all', l: 'All' }, { v: 'active', l: 'Active' }, { v: 'pending', l: 'Pending' }, { v: 'deactivated', l: 'Deactivated' }].map(f => (
              <span key={f.v} className={`chip ${statusFilter === f.v ? 'on' : ''}`} onClick={() => setStatusFilter(f.v)}>{f.l}</span>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="card">
          <table className="dt">
            <thead>
              <tr><th>ID</th><th>Name</th><th>Domain Expertise</th><th>Region / TZ</th><th>Seniority</th><th>Workload</th><th>Resolved</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: '#6b6b6b' }}>Loading...</td></tr>
              ) : engineers.length === 0 ? (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: '#6b6b6b' }}>No engineers found</td></tr>
              ) : engineers.map(eng => {
                const st = getStatus(eng)
                const loadPct = eng.max_ticket_capacity > 0 ? eng.active_ticket_count / eng.max_ticket_capacity : 0
                return (
                  <tr key={eng.id} style={{ opacity: !eng.is_active ? 0.55 : 1 }}>
                    <td><span className="mono small" style={{ color: '#174D38', fontWeight: 600 }}>{eng.engineer_id}</span></td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 24, height: 24, borderRadius: 4, background: '#174D38', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                          {eng.full_name.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 500 }}>{eng.full_name}</div>
                          <div className="tiny muted">{eng.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                        {eng.domain_expertise.slice(0, 3).map(d => (
                          <span key={d} className="pill">{DOMAINS.find(x => x.v === d)?.l || d}</span>
                        ))}
                        {eng.domain_expertise.length > 3 && <span className="pill">+{eng.domain_expertise.length - 3}</span>}
                      </div>
                    </td>
                    <td className="small">
                      {eng.city || eng.region}
                      <div className="tiny muted">{eng.region} · {eng.timezone}</div>
                    </td>
                    <td className="small" style={{ textTransform: 'capitalize' }}>{eng.seniority_level}</td>
                    <td style={{ width: 120 }}>
                      <div className="row" style={{ gap: 6 }}>
                        <span className="mono tiny" style={{ width: 32 }}>{eng.active_ticket_count}/{eng.max_ticket_capacity}</span>
                        <div className="bar" style={{ flex: 1 }}>
                          <div className="bar-f" style={{ width: `${loadPct * 100}%`, background: loadPct > 0.85 ? '#4D1717' : loadPct > 0.7 ? '#8a5a00' : '#174D38' }} />
                        </div>
                      </div>
                    </td>
                    <td className="mono small">{eng.total_resolved}</td>
                    <td><span className={`pill ${st.p}`}><span className={`dot ${st.c}`} />{st.l}</span></td>
                    <td>
                      {eng.is_active ? (
                        <button className="btn btn-sm btn-r" onClick={() => handleDeactivate(eng.engineer_id)}>Deactivate</button>
                      ) : (
                        <button className="btn btn-sm btn-p" onClick={() => handleReactivate(eng.engineer_id)}>Reactivate</button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Create Modal */}
        {showModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(20,20,20,.4)', zIndex: 100, display: 'grid', placeItems: 'center', backdropFilter: 'blur(2px)' }} onClick={() => setShowModal(false)}>
            <div className="adm card" onClick={e => e.stopPropagation()} style={{ width: 560, maxHeight: '90vh', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 12px 32px rgba(0,0,0,.14)' }}>
              <div className="c-head" style={{ background: '#174D38', borderRadius: '6px 6px 0 0', borderBottom: 'none' }}>
                <h3 style={{ color: '#fff' }}>Add New Engineer</h3>
                <span className="grow" />
                <button className="btn btn-sm btn-g" style={{ color: 'rgba(255,255,255,.7)' }} onClick={() => setShowModal(false)}>✕</button>
              </div>
              <form onSubmit={handleCreate} style={{ padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {error && <div style={{ padding: '8px 12px', background: '#f5eaea', border: '1px solid #4D1717', borderRadius: 4, color: '#4D1717', fontSize: 12 }}>{error}</div>}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><label className="lbl">Full Name</label><input placeholder="Arjun Sharma" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} required /></div>
                  <div><label className="lbl">Email</label><input type="email" placeholder="arjun@company.com" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required /></div>
                </div>
                <div>
                  <label className="lbl">Domain Expertise</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {DOMAINS.map(d => (
                      <span key={d.v} className={`chip ${form.domain_expertise.includes(d.v) ? 'on' : ''}`} onClick={() => toggleDomain(d.v)}>{d.l}</span>
                    ))}
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><label className="lbl">Region</label>
                    <select value={form.region} onChange={e => setForm(f => ({ ...f, region: e.target.value }))}>
                      {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div><label className="lbl">Timezone</label><input value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} /></div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div><label className="lbl">Seniority</label>
                    <select value={form.seniority_level} onChange={e => setForm(f => ({ ...f, seniority_level: e.target.value }))}>
                      {SENIORITY.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                    </select>
                  </div>
                  <div><label className="lbl">Max Capacity</label><input type="number" min={1} max={50} value={form.max_ticket_capacity} onChange={e => setForm(f => ({ ...f, max_ticket_capacity: parseInt(e.target.value) }))} /></div>
                </div>
                <div style={{ display: 'flex', gap: 8, paddingTop: 4 }}>
                  <button type="button" className="btn" style={{ flex: 1 }} onClick={() => setShowModal(false)}>Cancel</button>
                  <button type="submit" className="btn btn-p" style={{ flex: 2 }} disabled={creating}>{creating ? 'Creating...' : 'Create Engineer →'}</button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </>
  )
}