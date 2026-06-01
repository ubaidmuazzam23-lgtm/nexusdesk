'use client'
// File: frontend/src/app/admin/knowledge/page.tsx

import { useState, useEffect, useCallback, useRef } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Doc {
  id: string; title: string; filename: string; domain: string
  description: string; chunk_count: number; created_at: string
  uploaded_by: string; uploaded_by_role: string
}

const DOMAINS = [
  {v:'all',l:'All'},{v:'networking',l:'Networking'},{v:'hardware',l:'Hardware'},{v:'software',l:'Software'},
  {v:'security',l:'Security'},{v:'email_communication',l:'Email & Comm'},{v:'identity_access',l:'Identity & Access'},
  {v:'database',l:'Database'},{v:'cloud',l:'Cloud'},{v:'infrastructure',l:'Infrastructure'},{v:'devops',l:'DevOps'},
  {v:'erp_business_apps',l:'ERP & Business'},{v:'endpoint_management',l:'Endpoint Mgmt'},{v:'other',l:'Other'},
]

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .kb{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .kb *{box-sizing:border-box}
  .kb .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .kb .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:10px;min-height:40px}
  .kb .c-head h3{margin:0;font-size:12px;font-weight:600}
  .kb .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
  .kb .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .kb .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .kb .pill-pur{background:#f0edf8;color:#5b3d8a;border-color:transparent}
  .kb table.dt{width:100%;border-collapse:collapse;font-size:12px}
  .kb table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
  .kb table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .kb table.dt tr:hover td{background:#f9f9f9}
  .kb .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
  .kb .btn:hover{background:#EBEBEB}
  .kb .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .kb .btn-p:hover{background:#1f6a4d!important}
  .kb .btn-r{background:#4D1717!important;color:#fff!important;border-color:#4D1717!important}
  .kb .btn-sm{height:24px;padding:0 8px;font-size:11px}
  .kb .btn-g{background:transparent!important;border-color:transparent!important;color:#6b6b6b!important}
  .kb .chip{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:12px;background:#EBEBEB;border:1px solid #CBCBCB;font-size:11px;color:#3a3a3a;cursor:pointer;font-weight:500;transition:all .1s}
  .kb .chip:hover,.kb .chip.on{background:#174D38;color:#fff;border-color:#174D38}
  .kb .bar{height:5px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
  .kb .bar-f{height:100%;background:#174D38;transition:width .4s;border-radius:3px}
  .kb .mono{font-family:"JetBrains Mono",monospace}
  .kb .muted{color:#6b6b6b}
  .kb .small{font-size:11px}
  .kb .tiny{font-size:10px}
  .kb .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .kb .row{display:flex;align-items:center;gap:8px}
  .kb .grow{flex:1}
  .kb .lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-bottom:5px;display:block}
  .kb input,.kb select,.kb textarea{font-family:inherit;font-size:12px;background:#EBEBEB;border:1px solid #CBCBCB;color:#141414;border-radius:4px;padding:6px 10px;width:100%;outline:none;transition:border-color .15s}
  .kb input:focus,.kb select:focus,.kb textarea:focus{border-color:#174D38;background:#fff}
  .kb .upload-zone{border:1.5px dashed #CBCBCB;border-radius:6px;padding:24px;text-align:center;color:#6b6b6b;cursor:pointer;transition:all .2s}
  .kb .upload-zone:hover{border-color:#174D38;color:#174D38;background:#e8f2ed}
`

export default function KnowledgeBasePage() {
  const [docs, setDocs]           = useState<Doc[]>([])
  const [loading, setLoading]     = useState(true)
  const [uploading, setUploading] = useState(false)
  const [filter, setFilter]       = useState('all')
  const [showUpload, setShowUpload] = useState(false)
  const [success, setSuccess]     = useState('')
  const [error, setError]         = useState('')
  const [form, setForm]           = useState({ title: '', domain: 'networking', description: '' })
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const hdrs = useCallback(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token') || ''}` }), [])

  useEffect(() => { fetchDocs() }, [filter])

  const fetchDocs = async () => {
    setLoading(true)
    try {
      const p = filter !== 'all' ? `?domain=${filter}` : ''
      const r = await fetch(`${API}/api/v1/knowledge/documents${p}`, { headers: hdrs() })
      if (r.ok) setDocs(await r.json())
    } catch {} finally { setLoading(false) }
  }

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) { setError('Select a file'); return }
    if (!form.title.trim()) { setError('Title required'); return }
    setUploading(true); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file); fd.append('title', form.title)
      fd.append('domain', form.domain); fd.append('description', form.description)
      const r = await fetch(`${API}/api/v1/knowledge/upload`, { method: 'POST', headers: hdrs(), body: fd })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Failed')
      setSuccess(`"${d.title}" — ${d.chunk_count} chunks indexed.`)
      setShowUpload(false)
      setForm({ title: '', domain: 'networking', description: '' })
      if (fileRef.current) fileRef.current.value = ''
      fetchDocs()
    } catch (err: any) { setError(err.message) }
    finally { setUploading(false) }
  }

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`Delete "${title}"?`)) return
    const r = await fetch(`${API}/api/v1/knowledge/documents/${id}`, { method: 'DELETE', headers: hdrs() })
    if (r.ok) { setSuccess(`"${title}" deleted.`); fetchDocs() }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setSearching(true); setSearchResults([])
    try {
      const r = await fetch(`${API}/api/v1/knowledge/search`, {
        method: 'POST', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, n_results: 5 }),
      })
      if (r.ok) { const d = await r.json(); setSearchResults(d.results || []) }
    } catch {} finally { setSearching(false) }
  }

  const simColor = (s: number) => s >= 80 ? '#1a7a4a' : s >= 60 ? '#8a5a00' : s >= 40 ? '#2a6bab' : '#6b6b6b'

  const fmtDate = (iso: string) => {
    try { return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
    catch { return iso }
  }

  const fileTypeIcon = (filename: string) => {
    if (filename.endsWith('.pdf'))  return '📄'
    if (filename.endsWith('.docx')) return '📝'
    if (filename.endsWith('.md'))   return '📋'
    return '📃'
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="kb" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
          {[
            { l: 'Indexed Docs',     v: docs.length,                                                      d: 'in knowledge base' },
            { l: 'Auto-indexed',     v: docs.filter(d => d.uploaded_by_role === 'engineer_auto').length,  d: 'from resolved tickets' },
            { l: 'Manual Uploads',   v: docs.filter(d => d.uploaded_by_role !== 'engineer_auto').length,  d: 'by admin / engineer' },
            { l: 'Total Chunks',     v: docs.reduce((s, d) => s + d.chunk_count, 0),                      d: 'indexed text segments' },
          ].map((s, i) => (
            <div key={i} className="card" style={{ padding: '12px 16px' }}>
              <div style={{ fontSize: 10, color: '#6b6b6b', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: '"JetBrains Mono",monospace', fontWeight: 600 }}>{s.l}</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: '"JetBrains Mono",monospace', letterSpacing: '-.02em', marginTop: 4 }}>{s.v}</div>
              <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 2 }}>{s.d}</div>
            </div>
          ))}
        </div>

        {success && (
          <div style={{ padding: '8px 14px', background: '#e6f4ed', border: '1px solid #1a7a4a', borderRadius: 4, color: '#1a7a4a', fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
            {success}
            <button onClick={() => setSuccess('')} style={{ background: 'none', border: 'none', color: '#1a7a4a', cursor: 'pointer' }}>×</button>
          </div>
        )}

        {/* Documents */}
        <div className="card">
          <div className="c-head">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
            <h3>Documents</h3>
            <span className="grow" />
            <div className="row" style={{ gap: 6 }}>
              <input placeholder="Test query..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} style={{ width: 200 }} />
              <button className="btn btn-sm" onClick={handleSearch} disabled={searching}>{searching ? '...' : 'Search'}</button>
            </div>
            <button className="btn btn-sm btn-p" onClick={() => { setShowUpload(true); setError('') }}>+ Upload</button>
          </div>

          {/* Search results */}
          {searchResults.length > 0 && (
            <div style={{ padding: '10px 14px', borderBottom: '1px solid #CBCBCB', background: '#f9f9f9' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#6b6b6b', marginBottom: 8, fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                {searchResults.length} results for "{searchQuery}"
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {searchResults.map((r, i) => (
                  <div key={i} style={{ background: '#fff', border: '1px solid #CBCBCB', borderLeft: `3px solid ${simColor(r.cosine_similarity)}`, borderRadius: 4, padding: '8px 10px' }}>
                    <div className="row">
                      <span style={{ fontWeight: 600, fontSize: 12, flex: 1 }}>{r.title}</span>
                      <span style={{ fontSize: 10, fontFamily: '"JetBrains Mono",monospace', fontWeight: 700, color: simColor(r.cosine_similarity), padding: '1px 6px', background: `${simColor(r.cosine_similarity)}18`, borderRadius: 3 }}>{r.cosine_similarity}%</span>
                    </div>
                    <div style={{ fontSize: 11, color: '#6b6b6b', marginTop: 4, lineHeight: 1.6 }}>{r.content.slice(0, 200)}...</div>
                  </div>
                ))}
              </div>
              <button className="btn btn-sm btn-g" style={{ marginTop: 8 }} onClick={() => setSearchResults([])}>Clear results ×</button>
            </div>
          )}

          {/* Domain filter */}
          <div style={{ padding: '8px 14px', borderBottom: '1px solid #CBCBCB', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {DOMAINS.map(d => (
              <span key={d.v} className={`chip ${filter === d.v ? 'on' : ''}`} onClick={() => setFilter(d.v)} style={{ height: 20, fontSize: 10 }}>{d.l}</span>
            ))}
          </div>

          {/* Table */}
          <table className="dt">
            <thead>
              <tr><th>Document</th><th>Domain</th><th>Source</th><th>Chunks</th><th>Indexed</th><th></th></tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#6b6b6b' }}>Loading...</td></tr>
              ) : docs.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: 40, color: '#6b6b6b' }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>📚</div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>No documents yet</div>
                  <div style={{ fontSize: 12 }}>Upload PDF, TXT, Markdown or Word (.docx) files to build the RAG knowledge base.</div>
                </td></tr>
              ) : docs.map(doc => (
                <tr key={doc.id}>
                  <td>
                    <div className="row">
                      <span style={{ fontSize: 16 }}>{fileTypeIcon(doc.filename)}</span>
                      <div>
                        <div style={{ fontWeight: 500 }}>{doc.title}</div>
                        <div className="tiny muted mono">{doc.filename}</div>
                        {doc.description && <div className="tiny muted" style={{ marginTop: 2 }}>{doc.description}</div>}
                      </div>
                    </div>
                  </td>
                  <td><span className="pill">{DOMAINS.find(d => d.v === doc.domain)?.l || doc.domain}</span></td>
                  <td>
                    {doc.uploaded_by_role === 'engineer_auto'
                      ? <span className="pill pill-pur">Auto-indexed</span>
                      : <span className="pill pill-grn">Manual</span>}
                  </td>
                  <td className="mono small">{doc.chunk_count}</td>
                  <td className="small muted mono">{fmtDate(doc.created_at)}</td>
                  <td>
                    <button className="btn btn-sm btn-r" onClick={() => handleDelete(doc.id, doc.title)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Upload Modal */}
        {showUpload && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(20,20,20,.4)', zIndex: 100, display: 'grid', placeItems: 'center', backdropFilter: 'blur(2px)' }} onClick={() => setShowUpload(false)}>
            <div className="kb card" onClick={e => e.stopPropagation()} style={{ width: 500, overflow: 'hidden', boxShadow: '0 12px 32px rgba(0,0,0,.14)' }}>
              <div className="c-head" style={{ background: '#174D38', borderRadius: '6px 6px 0 0', borderBottom: 'none' }}>
                <h3 style={{ color: '#fff' }}>Upload Document</h3>
                <span className="grow" />
                <span style={{ fontSize: 11, color: 'rgba(255,255,255,.5)' }}>PDF · TXT · Markdown · Word · Max 20MB</span>
                <button className="btn btn-sm btn-g" style={{ color: 'rgba(255,255,255,.7)' }} onClick={() => setShowUpload(false)}>✕</button>
              </div>
              <form onSubmit={handleUpload} style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {error && (
                  <div style={{ padding: '8px 12px', background: '#f5eaea', border: '1px solid #4D1717', borderRadius: 4, color: '#4D1717', fontSize: 12 }}>{error}</div>
                )}
                <div>
                  <label className="lbl">File</label>
                  <input ref={fileRef} type="file" accept=".pdf,.txt,.md,.docx" />
                  <div style={{ fontSize: 10, color: '#6b6b6b', marginTop: 4 }}>Supported: .pdf, .txt, .md, .docx</div>
                </div>
                <div>
                  <label className="lbl">Title</label>
                  <input placeholder="e.g. Netskope DNS Routing Troubleshooting Guide" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} required />
                </div>
                <div>
                  <label className="lbl">Domain</label>
                  <select value={form.domain} onChange={e => setForm(f => ({ ...f, domain: e.target.value }))}>
                    {DOMAINS.filter(d => d.v !== 'all').map(d => <option key={d.v} value={d.v}>{d.l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="lbl">Description (optional)</label>
                  <textarea rows={2} placeholder="Brief description of this document..." value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="btn" style={{ flex: 1 }} onClick={() => setShowUpload(false)}>Cancel</button>
                  <button type="submit" className="btn btn-p" style={{ flex: 2 }} disabled={uploading}>{uploading ? 'Indexing...' : 'Upload & Index →'}</button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </>
  )
}