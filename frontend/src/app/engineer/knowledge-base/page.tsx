'use client'
// File: frontend/src/app/engineer/knowledge/page.tsx

import { useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface SearchResult {
  content: string; title: string; doc_id: string
  domain: string; cosine_similarity: number; filename: string
  description: string; summary?: string; allChunks?: string[]
}

const DOMAINS = [
  {v:'',l:'All Domains'},{v:'networking',l:'Networking'},{v:'hardware',l:'Hardware'},
  {v:'software',l:'Software'},{v:'security',l:'Security'},{v:'email_communication',l:'Email & Comm'},
  {v:'identity_access',l:'Identity & Access'},{v:'database',l:'Database'},{v:'cloud',l:'Cloud'},
  {v:'infrastructure',l:'Infrastructure'},{v:'devops',l:'DevOps'},
  {v:'erp_business_apps',l:'ERP & Business'},{v:'endpoint_management',l:'Endpoint Mgmt'},
]

// ── KB Content Renderer ───────────────────────────────────────────────────────
function KBContent({ text }: { text: string }) {
  const cleaned = (() => {
    let t = text.replace(/[●▪◆□]/g,'•').replace(/\t/g,'  ').replace(/^\d+$/gm,'').trim()
    const ratio = (t.match(/\n/g)||[]).length / (t.length/100)
    if (ratio < 1) {
      t = t.replace(/([.!?:])\s+(\d+[.:]\s+[A-Z])/g,'$1\n$2')
      t = t.replace(/([.!?])\s+(•\s)/g,'$1\n$2')
      t = t.replace(/\.\s+((?:Introduction|Summary|Overview|Conclusion|Background|Components|Architecture|Step|Note|Troubleshooting|Resolution|Root Cause|Preventive|References|Appendix|Symptoms|Diagnostic)\s*[\d.:)]*\s)/g,'.\n\n$1')
    }
    return t.replace(/\n{3,}/g,'\n\n').trim()
  })()

  const lines = cleaned.split('\n')
  const els: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i], tr = line.trim()
    if (!tr || tr.length <= 2) { els.push(<div key={i} style={{height:4}}/>); i++; continue }
    if (/^[─═\-]{4,}$/.test(tr)) { els.push(<hr key={i} style={{border:'none',borderTop:'1px solid #e4e7ec',margin:'10px 0'}}/>); i++; continue }
    const isAllCaps = tr===tr.toUpperCase() && tr.length>2 && tr.length<60 && !/https?:\/\//.test(tr) && !/^\d/.test(tr) && /[A-Z]/.test(tr) && tr.split(' ').length<=6
    if (isAllCaps) {
      els.push(<div key={i} style={{fontSize:10,fontWeight:700,textTransform:'uppercase',letterSpacing:'.12em',color:'#6b7280',fontFamily:'monospace',marginTop:els.length>0?14:0,marginBottom:6,paddingBottom:4,borderBottom:'1px solid #f0f0f0'}}>{tr}</div>)
      i++; continue
    }
    const numM = tr.match(/^(?:STEP\s+)?(\d+)[\.\:\)]\s+(.+)$/i)
    if (numM) {
      els.push(<div key={i} style={{display:'flex',gap:10,marginBottom:6,alignItems:'flex-start'}}><span style={{fontFamily:'monospace',fontSize:11,color:'#174D38',fontWeight:700,minWidth:20,flexShrink:0,paddingTop:1}}>{numM[1]}.</span><span style={{fontSize:13,lineHeight:1.65,color:'#374151',flex:1}}>{numM[2]}</span></div>)
      i++; continue
    }
    if (/^[•\-\*]\s+/.test(tr)) {
      els.push(<div key={i} style={{display:'flex',gap:8,marginBottom:4,alignItems:'flex-start'}}><span style={{color:'#174D38',fontWeight:700,fontSize:16,lineHeight:1,marginTop:1,flexShrink:0}}>·</span><span style={{fontSize:13,lineHeight:1.65,color:'#374151',flex:1}}>{tr.replace(/^[•\-\*]\s+/,'')}</span></div>)
      i++; continue
    }
    const kvM = tr.match(/^([A-Za-z][A-Za-z0-9\s&\/\-\.]{1,35}):\s+(.+)$/)
    if (kvM && !tr.startsWith('http')) {
      els.push(<div key={i} style={{display:'flex',gap:10,marginBottom:6,alignItems:'flex-start'}}><span style={{fontFamily:'monospace',fontSize:10,fontWeight:600,color:'#9ca3af',textTransform:'uppercase',letterSpacing:'.04em',minWidth:110,flexShrink:0,paddingTop:2}}>{kvM[1]}</span><span style={{fontSize:13,color:'#111827',lineHeight:1.55,flex:1}}>{kvM[2]}</span></div>)
      i++; continue
    }
    if (line.startsWith('  ') && tr && !/^[•\-]/.test(tr)) {
      els.push(<code key={i} style={{display:'block',fontFamily:'monospace',fontSize:11,color:'#174D38',background:'rgba(23,77,56,0.06)',padding:'3px 10px',borderRadius:4,marginBottom:3,wordBreak:'break-all' as any,borderLeft:'2px solid #174D38'}}>{tr}</code>)
      i++; continue
    }
    els.push(<div key={i} style={{fontSize:13,color:'#374151',lineHeight:1.7,marginBottom:3}}>{tr}</div>)
    i++
  }
  return <div>{els}</div>
}

export default function EngineerKnowledgePage() {
  const [query,    setQuery]    = useState('')
  const [domain,   setDomain]   = useState('')
  const [results,  setResults]  = useState<(SearchResult & {allChunks:string[]})[]>([])
  const [searching,setSearching]= useState(false)
  const [searched, setSearched] = useState(false)
  const [selected, setSelected] = useState<(SearchResult & {allChunks:string[]}) | null>(null)
  const [showFull, setShowFull] = useState(false)
  const [showUpload,setShowUpload]=useState(false)
  const [uploading,setUploading]=useState(false)
  const [uploadForm,setUploadForm]=useState({title:'',domain:'networking',description:''})
  const [uploadError,setUploadError]=useState('')
  const [uploadSuccess,setUploadSuccess]=useState('')

  const hdrs  = () => ({ Authorization:`Bearer ${localStorage.getItem('access_token')||''}` })
  const jhdrs = () => ({ ...hdrs(), 'Content-Type':'application/json' })

  const simColor = (s:number) => s>=80?'#16a34a':s>=60?'#ca8a04':s>=40?'#2563eb':'#9ca3af'
  const simLabel = (s:number) => s>=80?'High':s>=60?'Good':s>=40?'Fair':'Low'

  const search = async () => {
    if (!query.trim()) return
    setSearching(true); setSearched(false); setSelected(null); setShowFull(false)
    try {
      const r = await fetch(`${API}/api/v1/knowledge/search`,{method:'POST',headers:jhdrs(),body:JSON.stringify({query,n_results:20,domain:domain||undefined})})
      const d = await r.json()
      const raw: SearchResult[] = d.results || []
      // Deduplicate by doc_id — one card per document
      const seen = new Map<string, SearchResult & {allChunks:string[]}>()
      raw.forEach(r => {
        const key = r.doc_id || r.title
        if (!seen.has(key)) seen.set(key, {...r, allChunks:[r.content]})
        else {
          const ex = seen.get(key)!
          ex.allChunks.push(r.content)
          if (r.cosine_similarity > ex.cosine_similarity) seen.set(key,{...ex,cosine_similarity:r.cosine_similarity})
        }
      })
      setResults(Array.from(seen.values()))
    } catch { setResults([]) }
    finally { setSearching(false); setSearched(true) }
  }

  const handleFileUpload = async (e:React.FormEvent) => {
    e.preventDefault()
    const input = document.getElementById('eng-kb-file') as HTMLInputElement
    const file = input?.files?.[0]
    if (!file) { setUploadError('Select a file'); return }
    if (!uploadForm.title.trim()) { setUploadError('Title required'); return }
    setUploading(true); setUploadError('')
    try {
      const fd = new FormData()
      fd.append('file',file); fd.append('title',uploadForm.title)
      fd.append('domain',uploadForm.domain); fd.append('description',uploadForm.description)
      const r = await fetch(`${API}/api/v1/knowledge/upload`,{method:'POST',headers:hdrs(),body:fd})
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail||'Upload failed')
      setUploadSuccess(`"${d.title}" — ${d.chunk_count} chunks indexed.`)
      setShowUpload(false); setUploadForm({title:'',domain:'networking',description:''}); input.value=''
    } catch (err:any) { setUploadError(err.message) }
    finally { setUploading(false) }
  }

  const css = `
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,"Inter",sans-serif}
    ::-webkit-scrollbar{width:5px}
    ::-webkit-scrollbar-thumb{background:#e4e7ec;border-radius:3px}
    input,select,textarea{font-family:inherit}
    input:focus,textarea:focus{border-color:#174D38!important;outline:none}
    .doc-row{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid #f4f4f4;cursor:pointer;transition:background .1s;gap:14px}
    .doc-row:hover{background:#f9fafb}
    .doc-row.active{background:#f0fdf4;border-left:3px solid #174D38}
    .doc-row:last-child{border-bottom:none}
  `

  return (
    <>
      <style>{css}</style>
      <div style={{background:'#f6f7f9',minHeight:'100vh',fontFamily:'-apple-system,"Inter",sans-serif',color:'#0f1419',display:'flex',flexDirection:'column',height:'100vh',overflow:'hidden'}}>

        {/* Header */}
        <div style={{background:'#fff',borderBottom:'1px solid #e4e7ec',padding:'16px 24px',flexShrink:0}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
            <div>
              <div style={{fontSize:18,fontWeight:700,letterSpacing:'-.02em'}}>Knowledge Base</div>
              <div style={{fontSize:12,color:'#7a8699',marginTop:2}}>Semantic search across IT docs and resolved tickets</div>
            </div>
            <button onClick={()=>{setShowUpload(true);setUploadError('');setUploadSuccess('')}}
              style={{padding:'7px 14px',background:'#174D38',color:'#fff',border:'none',fontSize:12,fontWeight:600,cursor:'pointer',borderRadius:6,fontFamily:'inherit'}}>
              + Upload Doc
            </button>
          </div>
          {uploadSuccess && <div style={{padding:'8px 12px',background:'#f0fdf4',border:'1px solid #86efac',color:'#166534',fontSize:12,marginBottom:10,borderRadius:5}}>✓ {uploadSuccess}</div>}
          {/* Search bar */}
          <div style={{display:'flex',gap:8,marginBottom:10}}>
            <input style={{flex:1,padding:'9px 13px',background:'#f6f7f9',border:'1px solid #e4e7ec',color:'#0f1419',fontSize:13,borderRadius:6}}
              placeholder="Search docs... e.g. 'EC2 unreachable', 'Netskope routing', 'SSL certificate'"
              value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==='Enter'&&search()} />
            <button onClick={search} disabled={searching||!query.trim()}
              style={{padding:'9px 20px',background:!query.trim()||searching?'#f6f7f9':'#174D38',color:!query.trim()||searching?'#9ca3af':'#fff',border:'1px solid #e4e7ec',fontSize:12,fontWeight:600,cursor:!query.trim()||searching?'not-allowed':'pointer',borderRadius:6,fontFamily:'inherit',minWidth:90}}>
              {searching?'...':'Search'}
            </button>
          </div>
          {/* Domain filters */}
          <div style={{display:'flex',gap:4,flexWrap:'wrap'}}>
            {DOMAINS.map(d=>(
              <button key={d.v} onClick={()=>setDomain(d.v)}
                style={{padding:'2px 9px',background:domain===d.v?'rgba(23,77,56,0.08)':'transparent',border:`1px solid ${domain===d.v?'rgba(23,77,56,0.3)':'#e4e7ec'}`,color:domain===d.v?'#174D38':'#9ca3af',fontSize:11,cursor:'pointer',borderRadius:3,fontFamily:'inherit',fontWeight:domain===d.v?600:400}}>
                {d.l}
              </button>
            ))}
          </div>
        </div>

        {/* Body — split layout */}
        <div style={{flex:1,display:'flex',overflow:'hidden'}}>

          {/* Left — document list */}
          <div style={{width:selected?340:600,flexShrink:0,background:'#fff',borderRight:'1px solid #e4e7ec',overflowY:'auto',transition:'width .2s'}}>
            {searching && <div style={{padding:40,textAlign:'center',color:'#9ca3af',fontSize:13}}>Searching...</div>}
            {searched && !searching && results.length===0 && (
              <div style={{padding:'48px 20px',textAlign:'center'}}>
                <div style={{fontSize:24,marginBottom:8}}>🔍</div>
                <div style={{fontWeight:600,fontSize:13,marginBottom:3}}>No results found</div>
                <div style={{fontSize:12,color:'#9ca3af'}}>Try different keywords or a broader domain.</div>
              </div>
            )}
            {results.length>0 && (
              <>
                <div style={{padding:'10px 16px',fontSize:11,color:'#9ca3af',borderBottom:'1px solid #f0f0f0'}}>
                  {results.length} document{results.length!==1?'s':''} found
                </div>
                {results.map((r,i)=>(
                  <div key={i} className={`doc-row${selected?.doc_id===r.doc_id?' active':''}`}
                    onClick={()=>{setSelected(r);setShowFull(false)}}>
                    {/* Similarity bar */}
                    <div style={{width:3,height:36,borderRadius:2,background:simColor(r.cosine_similarity),flexShrink:0}}/>
                    <div style={{flex:1,minWidth:0}}>
                      <div style={{fontWeight:600,fontSize:13,color:'#0f1419',marginBottom:2,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                        {r.title}
                      </div>
                      <div style={{display:'flex',alignItems:'center',gap:6}}>
                        <span style={{fontSize:10,color:'#9ca3af',fontFamily:'monospace',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:140}}>
                          {r.filename}
                        </span>
                        <span style={{fontSize:9,padding:'1px 6px',background:'rgba(23,77,56,0.07)',color:'#174D38',borderRadius:3,fontWeight:600,flexShrink:0}}>
                          {DOMAINS.find(d=>d.v===r.domain)?.l||r.domain}
                        </span>
                      </div>
                    </div>
                    <div style={{textAlign:'right',flexShrink:0}}>
                      <div style={{fontSize:14,fontWeight:700,color:simColor(r.cosine_similarity),fontFamily:'monospace',lineHeight:1}}>
                        {r.cosine_similarity}%
                      </div>
                      <div style={{fontSize:9,color:simColor(r.cosine_similarity),textTransform:'uppercase',letterSpacing:'.05em',marginTop:1}}>
                        {simLabel(r.cosine_similarity)}
                      </div>
                    </div>
                    <div style={{color:'#d1d5db',fontSize:14,flexShrink:0}}>›</div>
                  </div>
                ))}
              </>
            )}
            {!searched && !searching && (
              <div style={{padding:'60px 20px',textAlign:'center'}}>
                <div style={{fontSize:36,marginBottom:12}}>📖</div>
                <div style={{fontWeight:600,fontSize:14,marginBottom:6}}>Search the knowledge base</div>
                <div style={{fontSize:12,color:'#9ca3af',maxWidth:280,margin:'0 auto',lineHeight:1.6}}>
                  Find runbooks, setup guides and troubleshooting docs.
                </div>
              </div>
            )}
          </div>

          {/* Right — document detail */}
          {selected ? (
            <div style={{flex:1,overflowY:'auto',background:'#fff'}}>
              {/* Detail header */}
              <div style={{padding:'18px 24px',borderBottom:'1px solid #e4e7ec',position:'sticky',top:0,background:'#fff',zIndex:10}}>
                <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12}}>
                  <div style={{flex:1}}>
                    <div style={{fontWeight:700,fontSize:16,letterSpacing:'-.02em',marginBottom:4}}>{selected.title}</div>
                    <div style={{display:'flex',alignItems:'center',gap:8}}>
                      <span style={{fontSize:10,color:'#9ca3af',fontFamily:'monospace'}}>{selected.filename}</span>
                      <span style={{fontSize:10,padding:'2px 7px',background:'rgba(23,77,56,0.07)',color:'#174D38',borderRadius:3,fontWeight:600}}>
                        {DOMAINS.find(d=>d.v===selected.domain)?.l||selected.domain}
                      </span>
                      <span style={{fontSize:11,fontWeight:700,color:simColor(selected.cosine_similarity),fontFamily:'monospace'}}>
                        {selected.cosine_similarity}% {simLabel(selected.cosine_similarity)}
                      </span>
                    </div>
                  </div>
                  <button onClick={()=>setSelected(null)}
                    style={{background:'none',border:'1px solid #e4e7ec',cursor:'pointer',color:'#9ca3af',fontSize:14,padding:'4px 10px',borderRadius:4,fontFamily:'inherit',flexShrink:0}}>
                    ✕
                  </button>
                </div>
                {/* Toggle buttons */}
                <div style={{display:'flex',gap:6,marginTop:12}}>
                  <button onClick={()=>setShowFull(false)}
                    style={{padding:'5px 12px',background:!showFull?'#174D38':'transparent',color:!showFull?'#fff':'#6b7280',border:'1px solid',borderColor:!showFull?'#174D38':'#e4e7ec',borderRadius:5,fontSize:11,fontWeight:600,cursor:'pointer',fontFamily:'inherit'}}>
                    AI Summary
                  </button>
                  <button onClick={()=>setShowFull(true)}
                    style={{padding:'5px 12px',background:showFull?'#174D38':'transparent',color:showFull?'#fff':'#6b7280',border:'1px solid',borderColor:showFull?'#174D38':'#e4e7ec',borderRadius:5,fontSize:11,fontWeight:600,cursor:'pointer',fontFamily:'inherit'}}>
                    Full Document
                  </button>
                </div>
              </div>

              {/* Detail body */}
              <div style={{padding:'20px 24px'}}>
                {!showFull ? (
                  /* AI Summary view */
                  selected.summary ? (
                    <div>
                      <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:14}}>
                        <div style={{width:7,height:7,borderRadius:'50%',background:'#174D38'}}/>
                        <span style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:'.1em',color:'#174D38'}}>AI-Generated Summary</span>
                      </div>
                      <div style={{fontSize:13,color:'#374151',lineHeight:1.8,whiteSpace:'pre-wrap',background:'#f9fafb',padding:'16px',borderRadius:8,border:'1px solid #f0f0f0'}}>
                        {selected.summary}
                      </div>
                      <div style={{marginTop:16,padding:'10px 14px',background:'rgba(23,77,56,0.03)',border:'1px solid rgba(23,77,56,0.1)',borderRadius:6,fontSize:12,color:'#6b7280'}}>
                        This summary was generated by AI. Click <b style={{color:'#174D38'}}>Full Document</b> above to view the complete technical content.
                      </div>
                    </div>
                  ) : (
                    <div style={{padding:'32px 20px',textAlign:'center',color:'#9ca3af'}}>
                      <div style={{fontSize:22,marginBottom:8}}>✨</div>
                      <div style={{fontSize:13,fontWeight:500,marginBottom:4}}>No AI summary available</div>
                      <div style={{fontSize:12}}>This document was uploaded before summary generation was added.</div>
                      <button onClick={()=>setShowFull(true)}
                        style={{marginTop:12,padding:'6px 14px',background:'#174D38',color:'#fff',border:'none',borderRadius:5,fontSize:12,fontWeight:600,cursor:'pointer',fontFamily:'inherit'}}>
                        View Full Document →
                      </button>
                    </div>
                  )
                ) : (
                  /* Full document view */
                  <div>
                    <div style={{fontSize:11,fontWeight:700,textTransform:'uppercase',letterSpacing:'.1em',color:'#9ca3af',marginBottom:16}}>
                      Full Document Content
                    </div>
                    <KBContent text={(selected.allChunks||[selected.content]).join('\n\n')} />
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{flex:1,display:'flex',alignItems:'center',justifyContent:'center',color:'#d1d5db',flexDirection:'column',gap:8,background:'#fafafa'}}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
              <div style={{fontSize:13,color:'#9ca3af'}}>Select a document to view</div>
            </div>
          )}
        </div>

        {/* Upload modal */}
        {showUpload && (
          <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.45)',zIndex:100,display:'flex',alignItems:'center',justifyContent:'center',padding:20}}>
            <div style={{background:'#fff',border:'1px solid #e4e7ec',borderRadius:10,width:'100%',maxWidth:460,boxShadow:'0 20px 60px rgba(0,0,0,.12)'}}>
              <div style={{padding:'14px 18px',borderBottom:'1px solid #f0f0f0',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <div>
                  <div style={{fontWeight:700,fontSize:14}}>Upload Document</div>
                  <div style={{fontSize:11,color:'#9ca3af',marginTop:1}}>PDF, TXT, Markdown · Max 20MB</div>
                </div>
                <button onClick={()=>{setShowUpload(false);setUploadError('')}} style={{background:'none',border:'none',color:'#9ca3af',fontSize:18,cursor:'pointer'}}>×</button>
              </div>
              <form onSubmit={handleFileUpload} style={{padding:'16px 18px',display:'flex',flexDirection:'column',gap:11}}>
                {uploadError && <div style={{padding:'7px 10px',background:'#fef2f2',border:'1px solid #fca5a5',color:'#dc2626',fontSize:12,borderRadius:4}}>{uploadError}</div>}
                {[
                  {label:'File',node:<input id="eng-kb-file" type="file" accept=".pdf,.txt,.md" style={{width:'100%',padding:'6px 10px',background:'#f6f7f9',border:'1px solid #e4e7ec',borderRadius:4,fontSize:12,cursor:'pointer',color:'#0f1419',fontFamily:'inherit'}}/>},
                  {label:'Title',node:<input style={{width:'100%',padding:'7px 10px',background:'#f6f7f9',border:'1px solid #e4e7ec',borderRadius:4,fontSize:12,color:'#0f1419',fontFamily:'inherit'}} placeholder="e.g. AWS EC2 Troubleshooting Guide" value={uploadForm.title} onChange={e=>setUploadForm(f=>({...f,title:e.target.value}))} required/>},
                  {label:'Domain',node:<select style={{width:'100%',padding:'7px 10px',background:'#f6f7f9',border:'1px solid #e4e7ec',borderRadius:4,fontSize:12,color:'#0f1419',fontFamily:'inherit',cursor:'pointer'}} value={uploadForm.domain} onChange={e=>setUploadForm(f=>({...f,domain:e.target.value}))}>{DOMAINS.filter(d=>d.v!=='').map(d=><option key={d.v} value={d.v}>{d.l}</option>)}</select>},
                  {label:'Description (optional)',node:<textarea style={{width:'100%',padding:'7px 10px',background:'#f6f7f9',border:'1px solid #e4e7ec',borderRadius:4,fontSize:12,color:'#0f1419',fontFamily:'inherit',minHeight:52,resize:'vertical' as any}} placeholder="Brief description..." value={uploadForm.description} onChange={e=>setUploadForm(f=>({...f,description:e.target.value}))}/>},
                ].map((f,fi)=>(
                  <div key={fi}>
                    <div style={{fontSize:10,fontWeight:700,textTransform:'uppercase' as any,letterSpacing:'.08em',color:'#9ca3af',marginBottom:4}}>{f.label}</div>
                    {f.node}
                  </div>
                ))}
                <div style={{display:'flex',gap:8,marginTop:2}}>
                  <button type="button" onClick={()=>{setShowUpload(false);setUploadError('')}} style={{flex:1,padding:'9px',background:'#fff',border:'1px solid #e4e7ec',color:'#9ca3af',fontSize:12,cursor:'pointer',borderRadius:5,fontFamily:'inherit'}}>Cancel</button>
                  <button type="submit" disabled={uploading} style={{flex:2,padding:'9px',background:uploading?'#f6f7f9':'#174D38',color:uploading?'#9ca3af':'#fff',border:'none',fontSize:12,fontWeight:600,cursor:uploading?'not-allowed':'pointer',borderRadius:5,fontFamily:'inherit'}}>
                    {uploading?'Indexing...':'Upload & Index →'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </>
  )
}