// Location: frontend/src/app/admin/assets/page.tsx
//
// REWRITTEN for dynamic multi-table asset registry.
//
// Layout:
//   - Stats bar across top (total assets, tables, running, production)
//   - Upload modal: admin types a display name + selects CSV
//   - Schema Intelligence panel (collapsible)
//   - Separate section per table — each with its own columns, search, delete
//   - Row detail slide-out panel showing ALL columns dynamically

'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

// ── Types ─────────────────────────────────────────────────────────────────────

interface TableMeta {
  id:           string
  table_name:   string
  display_name: string
  row_count:    number
  columns:      string[]
  column_roles: Record<string, string>
  last_upload:  string | null
  created_at:   string | null
}

interface TableData {
  total:   number
  rows:    Record<string, string>[]
  columns: string[]
}

interface SchemaMeta {
  total_assets: number
  tables:       { name: string; display: string; rows: number }[]
  columns:      Record<string, { distinct: number; samples: string[]; role: string; tables: string[] }>
}

// ── CSS ───────────────────────────────────────────────────────────────────────

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
.as *{box-sizing:border-box;margin:0;padding:0}
.as{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
.as .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.as .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px;flex-wrap:wrap}
.as .c-head h3{margin:0;font-size:13px;font-weight:600;letter-spacing:-.01em}
.as .stat-lbl{font-size:10px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.08em;font-family:"JetBrains Mono",monospace;font-weight:600}
.as .stat-v{font-size:22px;font-weight:700;letter-spacing:-.02em;font-family:"JetBrains Mono",monospace;margin-top:4px}
.as .pill{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
.as .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
.as .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
.as .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
.as .pill-blue{background:#e8f0fd;color:#1a56b0;border-color:transparent}
.as .pill-teal{background:#f0fdfa;color:#0d9488;border-color:transparent}
.as .pill-pur{background:#f5f3ff;color:#6d28d9;border-color:transparent}
.as .role-identifier{background:#e8f0fd;color:#1a56b0;border-color:transparent}
.as .role-environment{background:#fdf4e3;color:#8a5a00;border-color:transparent}
.as .role-team{background:#f0fdfa;color:#0d9488;border-color:transparent}
.as .role-contact_email{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
.as .role-manager_email{background:#f5f3ff;color:#6d28d9;border-color:transparent}
.as .role-region{background:#f5eaea;color:#4D1717;border-color:transparent}
.as .role-other{background:#EBEBEB;color:#6b6b6b;border-color:#CBCBCB}
.as table.dt{width:100%;border-collapse:collapse;font-size:12px}
.as table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:7px 10px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
.as table.dt td{padding:7px 10px;border-bottom:1px solid #f0f0f0;vertical-align:middle;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.as table.dt tr:hover td{background:#f9f9f9;cursor:pointer}
.as table.dt tr.sel td{background:#e8f2ed}
.as .skel{background:linear-gradient(90deg,#f0f0f0 25%,#e8e8e8 50%,#f0f0f0 75%);background-size:200% 100%;animation:shimmer 1.4s infinite;border-radius:3px;height:11px;display:inline-block}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.as .mono{font-family:"JetBrains Mono",monospace}
.as .muted{color:#6b6b6b}.as .small{font-size:11px}.as .tiny{font-size:10px}
.as .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.as .row{display:flex;align-items:center;gap:8px}
.as .grow{flex:1}
.as .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
.as .btn:hover{background:#EBEBEB}
.as .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
.as .btn-p:hover{background:#1f6a4d!important}
.as .btn-r{background:#4D1717!important;color:#fff!important;border-color:#4D1717!important}
.as .btn-r:hover{background:#6b2020!important}
.as .btn-sm{height:24px;padding:0 8px;font-size:11px}
.as input[type=search],.as input[type=text],.as select{height:28px;padding:0 8px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;font-family:inherit;font-size:12px;color:#141414;outline:none;transition:border-color .15s}
.as input[type=search]:focus,.as input[type=text]:focus,.as select:focus{border-color:#174D38}
.as .overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:100;display:flex;align-items:center;justify-content:center}
.as .modal{background:#fff;border-radius:8px;border:1px solid #CBCBCB;width:520px;max-height:88vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,.14)}
.as .modal-head{padding:16px 20px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;background:#fff;z-index:1}
.as .modal-head h2{margin:0;font-size:14px;font-weight:600}
.as .modal-body{padding:20px;display:flex;flex-direction:column;gap:14px}
.as .modal-foot{padding:14px 20px;border-top:1px solid #CBCBCB;display:flex;gap:8px;justify-content:flex-end;position:sticky;bottom:0;background:#fff}
.as .upload-zone{border:2px dashed #CBCBCB;border-radius:6px;padding:28px;text-align:center;cursor:pointer;transition:all .2s}
.as .upload-zone:hover,.as .upload-zone.drag{border-color:#174D38;background:#e8f2ed}
.as .chk{width:14px;height:14px;cursor:pointer;accent-color:#174D38}
.as .detail-panel{position:fixed;top:0;right:0;bottom:0;width:440px;background:#fff;border-left:1px solid #CBCBCB;box-shadow:-4px 0 16px rgba(0,0,0,.1);z-index:50;display:flex;flex-direction:column;overflow:hidden}
.as .dp-head{padding:14px 16px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.as .dp-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.as .dp-row{display:flex;flex-direction:column;gap:2px}
.as .dp-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;font-family:"JetBrains Mono",monospace}
.as .dp-val{font-size:12px;color:#141414;word-break:break-all}
.as .dp-sec{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-top:6px;padding-bottom:6px;border-bottom:1px solid #f0f0f0}
.as details summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600}
.as details summary::-webkit-details-marker{display:none}
.as details[open] summary::before{content:'▾ '}
.as details:not([open]) summary::before{content:'▸ '}
.as .tbl-section{display:flex;flex-direction:column;gap:0}
.as .tbl-header{padding:10px 14px;background:#fff;border:1px solid #CBCBCB;border-radius:6px 6px 0 0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.as .tbl-body{border:1px solid #CBCBCB;border-top:none;border-radius:0 0 6px 6px;overflow:hidden}
`

// ── Role pill helper ──────────────────────────────────────────────────────────

function RolePill({ role }: { role: string }) {
  const cls = `pill role-${role.replace(/_/g, '_')}` + (
    ['identifier','environment','team','contact_email','manager_email','region'].includes(role)
      ? '' : ' role-other'
  )
  return <span className={cls}>{role.replace(/_/g, ' ')}</span>
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AssetsPage() {
  const [tables, setTables]               = useState<TableMeta[]>([])
  const [tableData, setTableData]         = useState<Record<string, TableData>>({})
  const [schema, setSchema]               = useState<SchemaMeta | null>(null)
  const [loading, setLoading]             = useState(true)
  const [loadingTables, setLoadingTables] = useState<Record<string, boolean>>({})
  const [searches, setSearches]           = useState<Record<string, string>>({})
  const [selected, setSelected]           = useState<Record<string, Set<string>>>({})
  const [detail, setDetail]               = useState<{ table: string; row: Record<string, string> } | null>(null)
  const [showUpload, setShowUpload]       = useState(false)
  const [showConfirmDelete, setShowConfirmDelete] = useState<{ type: 'table' | 'all' | 'rows'; table?: string } | null>(null)
  const [uploadFile, setUploadFile]       = useState<File | null>(null)
  const [displayName, setDisplayName]     = useState('')
  const [forceNew, setForceNew]           = useState(false)
  const [uploading, setUploading]         = useState(false)
  const [deleting, setDeleting]           = useState(false)
  const [drag, setDrag]                   = useState(false)
  const [success, setSuccess]             = useState('')
  const [error, setError]                 = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  }), [])

  // ── Fetch all tables ────────────────────────────────────────────────────────

  const fetchTables = useCallback(async () => {
    setLoading(true)
    try {
      const [tR, sR] = await Promise.all([
        fetch(`${API}/api/v1/assets/tables`, { headers: hdrs() }),
        fetch(`${API}/api/v1/assets/schema`,  { headers: hdrs() }),
      ])
      if (tR.ok) setTables(await tR.json())
      if (sR.ok) setSchema(await sR.json())
    } catch {}
    finally { setLoading(false) }
  }, [hdrs])

  useEffect(() => { fetchTables() }, [fetchTables])

  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(''), 4000); return () => clearTimeout(t) }
  }, [success])

  // ── Fetch rows for a specific table ────────────────────────────────────────

  const fetchTableData = useCallback(async (tableName: string, search?: string) => {
    setLoadingTables(p => ({ ...p, [tableName]: true }))
    try {
      const params = new URLSearchParams({ limit: '200' })
      if (search) params.set('search', search)
      const r = await fetch(`${API}/api/v1/assets/table/${tableName}?${params}`, { headers: hdrs() })
      if (r.ok) {
        const d = await r.json()
        setTableData(p => ({ ...p, [tableName]: d }))
      }
    } catch {}
    finally { setLoadingTables(p => ({ ...p, [tableName]: false })) }
  }, [hdrs])

  useEffect(() => {
    tables.forEach(t => { if (!tableData[t.table_name]) fetchTableData(t.table_name) })
  }, [tables])

  // ── Upload ──────────────────────────────────────────────────────────────────

  const handleUpload = async () => {
    if (!uploadFile) { setError('Please select a CSV file'); return }
    if (!displayName.trim()) { setError('Please give this table a name'); return }
    setUploading(true); setError('')
    try {
      const form = new FormData()
      form.append('file', uploadFile)
      form.append('display_name', displayName.trim())
      form.append('force_new_table', String(forceNew))
      const r = await fetch(`${API}/api/v1/assets/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` },
        body: form,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Upload failed')
      setSuccess(d.message + ` (${d.inserted} rows)` + (d.merged ? ' — merged with existing table' : ''))
      setShowUpload(false); setUploadFile(null); setDisplayName(''); setForceNew(false)
      fetchTables()
      setTimeout(() => fetchTableData(d.table_name), 500)
    } catch (err: any) {
      setError(err.message || 'Upload failed')
    } finally { setUploading(false) }
  }

  // ── Delete handlers ─────────────────────────────────────────────────────────

  const handleDelete = async () => {
    if (!showConfirmDelete) return
    setDeleting(true); setError('')
    try {
      let r: Response
      const { type, table } = showConfirmDelete

      if (type === 'all') {
        r = await fetch(`${API}/api/v1/assets/all`, { method: 'DELETE', headers: hdrs() })
      } else if (type === 'table' && table) {
        r = await fetch(`${API}/api/v1/assets/table/${table}`, { method: 'DELETE', headers: hdrs() })
      } else if (type === 'rows' && table) {
        const ids = Array.from(selected[table] || [])
        r = await fetch(`${API}/api/v1/assets/table/${table}/rows`, {
          method: 'DELETE',
          headers: { ...hdrs(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids }),
        })
      } else return

      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Delete failed')
      setSuccess(d.message)
      setSelected(p => { const n = { ...p }; if (table) delete n[table]; return n })
      setShowConfirmDelete(null)
      if (type === 'all') {
        setTables([]); setTableData({}); setSchema(null)
      } else {
        fetchTables()
        if (table) fetchTableData(table)
      }
    } catch (err: any) { setError(err.message) }
    finally { setDeleting(false) }
  }

  // ── Row selection ───────────────────────────────────────────────────────────

  const toggleRow = (tableName: string, id: string) => {
    setSelected(p => {
      const s = new Set(p[tableName] || [])
      s.has(id) ? s.delete(id) : s.add(id)
      return { ...p, [tableName]: s }
    })
  }

  const toggleAll = (tableName: string) => {
    const rows = tableData[tableName]?.rows || []
    const cur  = selected[tableName] || new Set()
    if (cur.size === rows.length) {
      setSelected(p => ({ ...p, [tableName]: new Set() }))
    } else {
      setSelected(p => ({ ...p, [tableName]: new Set(rows.map(r => r.id)) }))
    }
  }

  // ── Search ──────────────────────────────────────────────────────────────────

  const handleSearch = (tableName: string, val: string) => {
    setSearches(p => ({ ...p, [tableName]: val }))
    fetchTableData(tableName, val)
  }

  // ── Drag-drop ───────────────────────────────────────────────────────────────

  const onFileDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f && f.name.endsWith('.csv')) { setUploadFile(f); setError('') }
    else setError('Only .csv files accepted')
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  const fmtDate = (s: string | null) =>
    s ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'

  const totalAssets = tables.reduce((sum, t) => sum + t.row_count, 0)

  // Identify key columns to show in table based on roles
  const getDisplayCols = (tbl: TableMeta): string[] => {
    const roleOrder = ['identifier', 'environment', 'team', 'application', 'region', 'ip', 'os', 'power_state', 'contact_email']
    const byRole: Record<string, string[]> = {}
    Object.entries(tbl.column_roles).forEach(([col, role]) => {
      if (!byRole[role]) byRole[role] = []
      byRole[role].push(col)
    })
    const result: string[] = []
    for (const role of roleOrder) {
      const cols = byRole[role] || []
      result.push(...cols.slice(0, 1)) // one column per role
      if (result.length >= 8) break
    }
    return result
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="as" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>Asset Registry</div>
            <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
              {tables.length} table{tables.length !== 1 ? 's' : ''} · {totalAssets} total assets
            </div>
          </div>
          <div className="row">
            <button className="btn btn-r btn-sm" onClick={() => setShowConfirmDelete({ type: 'all' })}>Delete All</button>
            <button className="btn btn-sm" onClick={fetchTables}>↻ Refresh</button>
            <button className="btn btn-p" onClick={() => { setShowUpload(true); setError('') }}>↑ Upload CSV</button>
          </div>
        </div>

        {/* Banners */}
        {success && (
          <div style={{ padding: '10px 14px', background: '#e6f4ed', border: '1px solid #b7dfc8', borderRadius: 4, fontSize: 13, color: '#1a7a4a' }}>
            ✓ {success}
          </div>
        )}
        {error && !showUpload && !showConfirmDelete && (
          <div style={{ padding: '10px 14px', background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 13, color: '#4D1717' }}>
            ✕ {error}
          </div>
        )}

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          {[
            { l: 'Total Assets',  v: totalAssets,   accent: '#174D38' },
            { l: 'Asset Tables',  v: tables.length, accent: '#1a56b0' },
            { l: 'Schema Columns',v: schema ? Object.keys(schema.columns).length : 0, accent: '#0d9488' },
            { l: 'Identifier Fields', v: schema ? Object.values(schema.columns).filter(c => c.role === 'identifier').length : 0, accent: '#8a5a00' },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: '12px 14px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: s.accent }} />
              <div className="stat-lbl">{s.l}</div>
              <div className="stat-v" style={{ color: s.accent }}>{s.v}</div>
            </div>
          ))}
        </div>

        {/* Schema Intelligence */}
        {schema && Object.keys(schema.columns).length > 0 && (
          <div className="card" style={{ padding: '12px 14px' }}>
            <details>
              <summary>
                <span style={{ color: '#0d9488', fontWeight: 600 }}>Schema Intelligence</span>
                <span style={{ fontSize: 10, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginLeft: 8, fontWeight: 400 }}>
                  {Object.keys(schema.columns).length} columns across {schema.tables.length} table(s) · {schema.total_assets} assets indexed
                </span>
              </summary>
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {Object.entries(schema.columns)
                  .sort((a, b) => a[1].distinct - b[1].distinct)
                  .map(([col, meta]) => (
                    <div key={col} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', background: '#f8f8f8', border: '1px solid #e8e8e8', borderRadius: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 11, fontFamily: '"JetBrains Mono",monospace', color: '#174D38', minWidth: 160 }}>{col}</span>
                      <RolePill role={meta.role} />
                      <span className="pill pill-teal" style={{ fontSize: 9 }}>{meta.distinct} distinct</span>
                      <span style={{ fontSize: 10, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace' }}>
                        {meta.samples.slice(0, 4).join(' · ')}
                      </span>
                    </div>
                  ))}
              </div>
            </details>
          </div>
        )}

        {/* Empty state */}
        {!loading && tables.length === 0 && (
          <div className="card" style={{ padding: '60px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📋</div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>No asset tables yet</div>
            <div className="small muted" style={{ marginBottom: 16 }}>Upload a CSV to create your first asset table</div>
            <button className="btn btn-p btn-sm" onClick={() => setShowUpload(true)}>↑ Upload CSV</button>
          </div>
        )}

        {/* One section per table */}
        {tables.map(tbl => {
          const data      = tableData[tbl.table_name]
          const isLoading = loadingTables[tbl.table_name]
          const selSet    = selected[tbl.table_name] || new Set()
          const displayCols = getDisplayCols(tbl)
          const rows      = data?.rows || []

          return (
            <div key={tbl.table_name} className="tbl-section">
              {/* Table header */}
              <div className="tbl-header">
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{tbl.display_name}</div>
                  <div style={{ fontSize: 10, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
                    {tbl.table_name} · {tbl.row_count} rows · {tbl.columns.length} columns · last upload {fmtDate(tbl.last_upload)}
                  </div>
                </div>
                <span style={{ flex: 1 }} />
                {selSet.size > 0 && (
                  <button className="btn btn-r btn-sm" onClick={() => setShowConfirmDelete({ type: 'rows', table: tbl.table_name })}>
                    Delete {selSet.size} rows
                  </button>
                )}
                <input
                  type="search"
                  placeholder="Search…"
                  value={searches[tbl.table_name] || ''}
                  onChange={e => handleSearch(tbl.table_name, e.target.value)}
                  style={{ width: 180 }}
                />
                <button className="btn btn-r btn-sm" onClick={() => setShowConfirmDelete({ type: 'table', table: tbl.table_name })}>
                  Delete Table
                </button>
              </div>

              {/* Table body */}
              <div className="tbl-body">
                {isLoading ? (
                  <table className="dt">
                    <thead><tr>{displayCols.map(c => <th key={c}>{c}</th>)}</tr></thead>
                    <tbody>
                      {Array.from({ length: 4 }).map((_, i) => (
                        <tr key={i}>{displayCols.map((_, j) => (
                          <td key={j}><span className="skel" style={{ width: `${50 + Math.random() * 40}%` }} /></td>
                        ))}</tr>
                      ))}
                    </tbody>
                  </table>
                ) : rows.length === 0 ? (
                  <div style={{ padding: 32, textAlign: 'center', color: '#6b6b6b', fontSize: 12 }}>
                    No rows found
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="dt">
                      <thead>
                        <tr>
                          <th style={{ width: 32 }}>
                            <input type="checkbox" className="chk"
                              checked={selSet.size === rows.length && rows.length > 0}
                              onChange={() => toggleAll(tbl.table_name)} />
                          </th>
                          {displayCols.map(col => (
                            <th key={col}>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                <span>{col.replace(/_/g, ' ')}</span>
                                {tbl.column_roles[col] && (
                                  <span style={{ fontSize: 8, color: '#9ca3af', fontWeight: 400, textTransform: 'none' }}>
                                    {tbl.column_roles[col]}
                                  </span>
                                )}
                              </div>
                            </th>
                          ))}
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(row => (
                          <tr key={row.id} className={selSet.has(row.id) ? 'sel' : ''}>
                            <td onClick={e => { e.stopPropagation(); toggleRow(tbl.table_name, row.id) }}>
                              <input type="checkbox" className="chk"
                                checked={selSet.has(row.id)}
                                onChange={() => toggleRow(tbl.table_name, row.id)}
                                onClick={e => e.stopPropagation()} />
                            </td>
                            {displayCols.map(col => (
                              <td key={col} onClick={() => setDetail({ table: tbl.table_name, row })}>
                                <span title={row[col] || ''}>{row[col] || '—'}</span>
                              </td>
                            ))}
                            <td onClick={e => e.stopPropagation()}>
                              <button className="btn btn-sm btn-r"
                                onClick={() => { setSelected(p => ({ ...p, [tbl.table_name]: new Set([row.id]) })); setShowConfirmDelete({ type: 'rows', table: tbl.table_name }) }}>
                                Delete
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Row Detail Panel ─────────────────────────────────────────────────── */}
      {detail && (() => {
        const tbl = tables.find(t => t.table_name === detail.table)
        return (
          <>
            <div style={{ position: 'fixed', inset: 0, zIndex: 49 }} onClick={() => setDetail(null)} />
            <div className="as detail-panel">
              <div className="dp-head">
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    {detail.row[tbl?.columns.find(c => tbl.column_roles[c] === 'identifier') || ''] || 'Asset Detail'}
                  </div>
                  <div className="tiny muted mono">{tbl?.display_name}</div>
                </div>
                <button className="btn btn-sm" onClick={() => setDetail(null)}>✕</button>
              </div>
              <div className="dp-body">
                {/* Group columns by role */}
                {tbl && (() => {
                  const byRole: Record<string, string[]> = {}
                  tbl.columns.forEach(col => {
                    const role = tbl.column_roles[col] || 'other'
                    if (!byRole[role]) byRole[role] = []
                    byRole[role].push(col)
                  })

                  const roleOrder = [
                    ['identifier', 'Identity'],
                    ['environment', 'Environment'],
                    ['application', 'Application'],
                    ['team', 'Team'],
                    ['region', 'Location'],
                    ['ip', 'Network'],
                    ['os', 'System'],
                    ['power_state', 'Status'],
                    ['contact_email', 'Primary Contact'],
                    ['manager_email', 'Management'],
                    ['director_email', 'Management'],
                    ['ops_email', 'Operations'],
                    ['other', 'Additional Info'],
                  ]

                  const rendered: string[] = []
                  const sections: React.ReactNode[] = []

                  for (const [role, label] of roleOrder) {
                    const cols = byRole[role]?.filter(c => !rendered.includes(c)) || []
                    if (cols.length === 0) continue
                    cols.forEach(c => rendered.push(c))

                    sections.push(
                      <div key={role}>
                        <div className="dp-sec">{label}</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                          {cols.map(col => (
                            <div key={col} className="dp-row">
                              <div className="dp-lbl">{col.replace(/_/g, ' ')}</div>
                              <div className="dp-val">{detail.row[col] || '—'}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  }
                  return sections
                })()}
              </div>
            </div>
          </>
        )
      })()}

      {/* ── Upload Modal ─────────────────────────────────────────────────────── */}
      {showUpload && (
        <div className="as overlay" onClick={() => { setShowUpload(false); setError(''); setUploadFile(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h2>Upload Asset CSV</h2>
              <button className="btn btn-sm" style={{ border: 'none', background: 'none' }}
                onClick={() => { setShowUpload(false); setError(''); setUploadFile(null) }}>✕</button>
            </div>
            <div className="modal-body">
              {error && (
                <div style={{ padding: '8px 12px', background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 12, color: '#4D1717' }}>
                  ✕ {error}
                </div>
              )}

              <div style={{ padding: '10px 12px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 4, fontSize: 12, color: '#1a56b0' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Any CSV structure is supported</div>
                The AI will analyse your columns, assign semantic roles (identifier, environment, team, contact email etc.) and decide if this CSV can merge with an existing table.
              </div>

              {/* Table name */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', display: 'block', marginBottom: 6 }}>
                  Table Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Network Assets, SAP Servers, DC Mumbai..."
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  style={{ width: '100%', height: 36, padding: '0 12px', border: '1px solid #CBCBCB', borderRadius: 4, fontFamily: 'inherit', fontSize: 13, outline: 'none' }}
                />
              </div>

              {/* Drop zone */}
              <div
                className={`upload-zone ${drag ? 'drag' : ''}`}
                onDragOver={e => { e.preventDefault(); setDrag(true) }}
                onDragLeave={() => setDrag(false)}
                onDrop={onFileDrop}
                onClick={() => fileRef.current?.click()}
              >
                <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }}
                  onChange={e => { const f = e.target.files?.[0] || null; setUploadFile(f); setError('') }} />
                {uploadFile ? (
                  <div>
                    <div style={{ fontSize: 24, marginBottom: 8 }}>📄</div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1a7a4a' }}>{uploadFile.name}</div>
                    <div style={{ fontSize: 11, color: '#6b6b6b', marginTop: 4 }}>{(uploadFile.size / 1024).toFixed(1)} KB · Click to change</div>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 24, marginBottom: 8 }}>📂</div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Drop CSV here or click to browse</div>
                    <div style={{ fontSize: 11, color: '#6b6b6b', marginTop: 4 }}>Max 20MB · .csv only · Any column structure</div>
                  </div>
                )}
              </div>

              {/* Existing tables info */}
              {tables.length > 0 && (
                <div style={{ padding: '10px 12px', background: '#f0fdfa', border: '1px solid #99f6e4', borderRadius: 4 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: '#0d9488', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
                    Existing Tables — AI will check if this CSV can merge
                  </div>
                  {tables.map(t => (
                    <div key={t.table_name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                      <span style={{ fontWeight: 500 }}>{t.display_name}</span>
                      <span className="muted">{t.row_count} rows · {t.columns.length} cols</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Force new table toggle */}
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 12px',
                background: forceNew ? '#eff6ff' : '#FAFAFA', border: `1px solid ${forceNew ? '#bfdbfe' : '#CBCBCB'}`, borderRadius: 4 }}>
                <input type="checkbox" className="chk" checked={forceNew} onChange={e => setForceNew(e.target.checked)} style={{ marginTop: 2 }} />
                <div onClick={() => setForceNew(f => !f)} style={{ cursor: 'pointer' }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>Always create new table</div>
                  <div style={{ fontSize: 11, color: '#6b6b6b', marginTop: 2 }}>Skip the AI merge check and create a fresh table</div>
                </div>
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => { setShowUpload(false); setError(''); setUploadFile(null) }}>Cancel</button>
              <button className="btn btn-p" disabled={!uploadFile || !displayName.trim() || uploading} onClick={handleUpload}>
                {uploading ? 'Uploading…' : 'Upload & Analyse →'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Confirm Delete Modal ─────────────────────────────────────────────── */}
      {showConfirmDelete && (
        <div className="as overlay" onClick={() => setShowConfirmDelete(null)}>
          <div className="modal" style={{ width: 400 }} onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h2 style={{ color: '#4D1717' }}>
                {showConfirmDelete.type === 'all' ? 'Delete All Tables' :
                 showConfirmDelete.type === 'table' ? 'Delete Table' : 'Delete Rows'}
              </h2>
              <button className="btn btn-sm" style={{ border: 'none', background: 'none' }} onClick={() => setShowConfirmDelete(null)}>✕</button>
            </div>
            <div className="modal-body">
              {error && <div style={{ padding: '8px 12px', background: '#f5eaea', borderRadius: 4, fontSize: 12, color: '#4D1717' }}>{error}</div>}
              <div style={{ padding: 14, background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 13, color: '#4D1717' }}>
                {showConfirmDelete.type === 'all'
                  ? `This will permanently drop all ${tables.length} asset tables and delete all ${totalAssets} rows.`
                  : showConfirmDelete.type === 'table'
                  ? `This will permanently drop the "${tables.find(t => t.table_name === showConfirmDelete.table)?.display_name}" table and all its rows.`
                  : `This will permanently delete ${(selected[showConfirmDelete.table!] || new Set()).size} selected rows.`}
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={() => setShowConfirmDelete(null)}>Cancel</button>
              <button className="btn btn-r" disabled={deleting} onClick={handleDelete}>
                {deleting ? 'Deleting…' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}