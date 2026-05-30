// Location: ./frontend/src/app/manager/knowledge/page.tsx
'use client'

import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface SearchResult {
  content: string; title: string; doc_id: string
  domain: string; cosine_similarity: number
  filename: string; description: string
}

const DOMAINS = [
  { v: '', l: 'All Domains' }, { v: 'networking', l: 'Networking' },
  { v: 'hardware', l: 'Hardware' }, { v: 'software', l: 'Software' },
  { v: 'security', l: 'Security' }, { v: 'email_communication', l: 'Email & Comm' },
  { v: 'identity_access', l: 'Identity & Access' }, { v: 'database', l: 'Database' },
  { v: 'cloud', l: 'Cloud' }, { v: 'infrastructure', l: 'Infrastructure' },
  { v: 'devops', l: 'DevOps' }, { v: 'erp_business_apps', l: 'ERP & Business' },
  { v: 'endpoint_management', l: 'Endpoint Mgmt' },
]

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .mk *{box-sizing:border-box}
  .mk{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
  .mk .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .mk .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px}
  .mk .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
  .mk .mono{font-family:"JetBrains Mono",monospace}
  .mk .muted{color:#6b6b6b}.mk .small{font-size:11px}.mk .tiny{font-size:10px}
  .mk .pill{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB}
  .mk .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
  .mk .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
  .mk .grow{flex:1}
  .mk .row{display:flex;align-items:center;gap:8px}
  .mk input,.mk select{height:32px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;font-family:inherit;font-size:13px;color:#141414;outline:none;transition:border-color .15s}
  .mk input:focus,.mk select:focus{border-color:#174D38}
  .mk .btn{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 14px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;transition:background .1s}
  .mk .btn:hover{background:#EBEBEB}
  .mk .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
  .mk .btn:disabled{background:#EBEBEB!important;color:#a0a0a0!important;cursor:not-allowed}
`

export default function ManagerKnowledgePage() {
  const [query,     setQuery]     = useState('')
  const [domain,    setDomain]    = useState('')
  const [results,   setResults]   = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searched,  setSearched]  = useState(false)
  const [expanded,  setExpanded]  = useState<number | null>(null)

  const hdrs = () => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
    'Content-Type': 'application/json',
  })

  const search = async () => {
    if (!query.trim()) return
    setSearching(true); setSearched(false)
    try {
      const r = await fetch(`${API}/api/v1/knowledge/search`, {
        method: 'POST', headers: hdrs(),
        body: JSON.stringify({ query, n_results: 8, domain: domain || undefined }),
      })
      const d = await r.json()
      setResults(d.results || [])
    } catch { setResults([]) }
    finally { setSearching(false); setSearched(true) }
  }

  const simPill = (s: number) => s >= 80 ? 'pill-ok' : s >= 50 ? 'pill-warn' : ''
  const simLabel = (s: number) => s >= 80 ? 'High' : s >= 50 ? 'Good' : 'Low'

  return (
    <>
      <style>{CSS}</style>
      <div className="mk" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

        <div>
          <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em' }}>Knowledge Base</div>
          <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginTop: 1 }}>
            Search resolved tickets and documentation
          </div>
        </div>

        {/* Search */}
        <div className="card" style={{ padding: '14px' }}>
          <div className="row">
            <input
              style={{ flex: 1 }}
              placeholder="Search for solutions, fixes, procedures..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && search()}
            />
            <select value={domain} onChange={e => setDomain(e.target.value)} style={{ width: 150, fontFamily: '"JetBrains Mono",monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: '.04em' }}>
              {DOMAINS.map(d => <option key={d.v} value={d.v}>{d.l}</option>)}
            </select>
            <button className={`btn ${!searching && query.trim() ? 'btn-p' : ''}`} onClick={search} disabled={searching || !query.trim()}>
              {searching ? 'Searching...' : 'Search →'}
            </button>
          </div>
        </div>

        {/* Results */}
        {searched && (
          results.length === 0 ? (
            <div className="card" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b', fontSize: 12 }}>
              No results found. Try different keywords.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace' }}>{results.length} results</div>
              {results.map((r, i) => (
                <div key={r.doc_id + i} className="card" style={{ overflow: 'hidden' }}>
                  <div
                    style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
                    onClick={() => setExpanded(expanded === i ? null : i)}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, marginBottom: 2 }}>{r.title}</div>
                      <div style={{ fontSize: 11, color: '#6b6b6b' }}>{r.filename} · {r.domain}</div>
                    </div>
                    <span className={`pill ${simPill(r.cosine_similarity)}`}>
                      {r.cosine_similarity}% · {simLabel(r.cosine_similarity)}
                    </span>
                    <span style={{ color: '#6b6b6b', fontSize: 11 }}>{expanded === i ? '▲' : '▼'}</span>
                  </div>
                  {expanded === i && (
                    <div style={{ padding: '0 14px 14px', borderTop: '1px solid #f0f0f0' }}>
                      <div style={{ marginTop: 10, fontSize: 12, color: '#3a3a3a', lineHeight: 1.7, whiteSpace: 'pre-wrap', background: '#FAFAFA', padding: 10, borderRadius: 4, border: '1px solid #EBEBEB' }}>
                        {r.content}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </>
  )
}