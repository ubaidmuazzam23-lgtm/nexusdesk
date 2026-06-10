'use client'
// File: frontend/src/app/admin/overview/page.tsx

import { useState, useEffect } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface SlackOverview {
  total: number; open: number; in_progress: number; resolved: number
  unresolved: number; ai_solved: number; routed: number
  ai_pct: number; routed_pct: number
  this_week: number; this_month: number
  domains:     { domain:string; label:string; total:number; resolved:number; open:number; ai_tried:number }[]
  priorities:  { priority:string; total:number; resolved:number }[]
  time_series: { date:string; label:string; created:number; ai_solved:number; routed:number }[]
  recent:      { ticket_number:string; title:string; domain:string; priority:string; status:string; engineer_name:string|null; ai_attempted:boolean; ai_resolved:boolean; user_city:string|null; created_at:string }[]
}

const pColor = (p:string) =>
  p==='critical'?'#BE123C':p==='high'?'#D97706':p==='medium'?'#174D38':'#6b6b6b'

const pPill = (p:string) =>
  p==='critical'?'p-crit':p==='high'?'p-warn':p==='medium'?'p-ok':'p-grey'

const sPill = (s:string) =>
  s==='resolved'?'p-ok':s==='in_progress'?'p-blue':'p-warn'

export default function OverviewPage() {
  const [data,       setData]       = useState<SlackOverview | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [lastUpdate, setLastUpdate] = useState(new Date())

  const hdrs = () => ({ Authorization: `Bearer ${localStorage.getItem('access_token')||''}` })

  const fetchData = async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/analytics/slack-overview`, { headers: hdrs() })
      if (r.ok) { setData(await r.json()); setLastUpdate(new Date()) }
    } catch {}
    finally { setLoading(false) }
  }

  useEffect(() => { fetchData() }, [])

  const maxDomain = data ? Math.max(...data.domains.map(d=>d.total), 1) : 1
  const maxTime   = data ? Math.max(...data.time_series.map(d=>Math.max(d.created,d.ai_solved,d.routed)), 1) : 1

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
        .ov *{box-sizing:border-box}
        .ov{font-family:"IBM Plex Sans","Helvetica Neue",sans-serif;font-size:13px;color:#141414}
        .ov .card{background:#fff;border:1px solid #e0e0e0;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.05)}
        .ov .mono{font-family:"IBM Plex Mono",monospace}
        .ov .muted{color:#888}
        .ov .small{font-size:11px}
        .ov .tiny{font-size:10px}
        .ov .lbl{font-family:"IBM Plex Mono",monospace;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#888}
        .ov .pill{display:inline-flex;align-items:center;height:18px;padding:0 7px;font-family:"IBM Plex Mono",monospace;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;border-radius:2px;white-space:nowrap}
        .ov .p-ok{background:#e8f5ee;color:#1a7a4a}
        .ov .p-warn{background:#fdf3e3;color:#b45309}
        .ov .p-crit{background:#fef2f2;color:#BE123C}
        .ov .p-blue{background:#eff6ff;color:#1d4ed8}
        .ov .p-grey{background:#f0f0f0;color:#555}
        .ov .p-purple{background:#f5f3ff;color:#7c3aed}
        .ov table.dt{width:100%;border-collapse:collapse;font-size:12px}
        .ov table.dt th{text-align:left;font-family:"IBM Plex Mono",monospace;font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#888;padding:8px 14px;background:#f8f8f8;border-bottom:1px solid #ececec;font-weight:600;white-space:nowrap}
        .ov table.dt td{padding:8px 14px;border-bottom:1px solid #f4f4f4;vertical-align:middle}
        .ov table.dt tr:last-child td{border-bottom:none}
        .ov .bar-bg{height:4px;background:#f0f0f0;border-radius:2px;overflow:hidden}
        .ov .bar-fill{height:100%;border-radius:2px;transition:width .4s}
        .ov .ch-head{padding:12px 16px;border-bottom:1px solid #ececec;display:flex;align-items:center;gap:8px}
        .ov .ch-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
        .ov .btn{height:28px;padding:0 11px;border-radius:3px;font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:500;cursor:pointer}
      `}</style>

      <div className="ov" style={{display:'flex',flexDirection:'column',gap:16}}>

        {/* Header */}
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <div>
            <div style={{fontSize:15,fontWeight:600,letterSpacing:'-.02em'}}>Slack Analytics</div>
            <div className="tiny muted mono" style={{marginTop:2}}>
              All tickets · engineers · resolutions via Slack bot — updated {lastUpdate.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
            </div>
          </div>
          <div style={{flex:1}}/>
          <button onClick={fetchData} disabled={loading} className="btn" style={{
            border:'1px solid #174D38',background:'#e8f2ed',color:'#174D38',
          }}>
            {loading ? '…' : '↻ Refresh'}
          </button>
        </div>

        {loading && !data && (
          <div style={{padding:60,textAlign:'center',color:'#888',fontSize:13,fontFamily:'"IBM Plex Mono",monospace'}}>
            Loading...
          </div>
        )}

        {data && (
          <>
            {/* ── 3 Hero Stats ── */}
            <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12}}>

              {/* Total Tickets */}
              <div className="card" style={{padding:'24px 28px',position:'relative',overflow:'hidden'}}>
                <div style={{position:'absolute',top:0,left:0,right:0,height:3,background:'#174D38'}}/>
                <div className="lbl">Total Tickets</div>
                <div style={{fontSize:52,fontWeight:600,fontFamily:'"IBM Plex Mono",monospace',letterSpacing:'-.04em',lineHeight:1,marginTop:8,color:'#111'}}>
                  {data.total.toLocaleString()}
                </div>
                <div style={{display:'flex',gap:0,marginTop:16,borderTop:'1px solid #f0f0f0',paddingTop:14}}>
                  {[
                    {l:'This Week', v:data.this_week,   c:'#111'},
                    {l:'Month',     v:data.this_month,  c:'#111'},
                    {l:'Open',      v:data.open,        c:'#D97706'},
                    {l:'Active',    v:data.in_progress, c:'#1d4ed8'},
                  ].map((s,i) => (
                    <div key={i} style={{flex:1,borderLeft:i>0?'1px solid #f0f0f0':'none',paddingLeft:i>0?12:0}}>
                      <div className="lbl" style={{fontSize:9}}>{s.l}</div>
                      <div style={{fontSize:20,fontWeight:600,fontFamily:'"IBM Plex Mono",monospace',marginTop:2,color:s.c}}>{s.v}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* AI Solved */}
              <div className="card" style={{padding:'24px 28px',position:'relative',overflow:'hidden'}}>
                <div style={{position:'absolute',top:0,left:0,right:0,height:3,background:'#1a7a4a'}}/>
                <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:8}}>
                  <div className="lbl">AI Solved</div>
                  <span className="pill p-ok" style={{marginLeft:'auto'}}>No engineer needed</span>
                </div>
                <div style={{fontSize:52,fontWeight:600,fontFamily:'"IBM Plex Mono",monospace',letterSpacing:'-.04em',lineHeight:1,color:'#1a7a4a'}}>
                  {data.ai_solved.toLocaleString()}
                </div>
                <div style={{marginTop:16}}>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
                    <span className="tiny muted mono" style={{textTransform:'uppercase',letterSpacing:'.06em'}}>of all resolved tickets</span>
                    <span style={{fontFamily:'"IBM Plex Mono",monospace',fontSize:13,fontWeight:600,color:'#1a7a4a'}}>{data.ai_pct}%</span>
                  </div>
                  <div className="bar-bg" style={{height:6}}>
                    <div className="bar-fill" style={{width:`${data.ai_pct}%`,background:'#1a7a4a'}}/>
                  </div>
                  <div className="tiny muted mono" style={{marginTop:8}}>
                    Bot resolved without routing to any engineer
                  </div>
                </div>
              </div>

              {/* Routed to Engineer */}
              <div className="card" style={{padding:'24px 28px',position:'relative',overflow:'hidden'}}>
                <div style={{position:'absolute',top:0,left:0,right:0,height:3,background:'#D97706'}}/>
                <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:8}}>
                  <div className="lbl">Routed to Engineer</div>
                  <span className="pill p-warn" style={{marginLeft:'auto'}}>Human assigned</span>
                </div>
                <div style={{fontSize:52,fontWeight:600,fontFamily:'"IBM Plex Mono",monospace',letterSpacing:'-.04em',lineHeight:1,color:'#D97706'}}>
                  {data.routed.toLocaleString()}
                </div>
                <div style={{marginTop:16}}>
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
                    <span className="tiny muted mono" style={{textTransform:'uppercase',letterSpacing:'.06em'}}>of all resolved tickets</span>
                    <span style={{fontFamily:'"IBM Plex Mono",monospace',fontSize:13,fontWeight:600,color:'#D97706'}}>{data.routed_pct}%</span>
                  </div>
                  <div className="bar-bg" style={{height:6}}>
                    <div className="bar-fill" style={{width:`${data.routed_pct}%`,background:'#D97706'}}/>
                  </div>
                  <div className="tiny muted mono" style={{marginTop:8}}>
                    Escalated to network engineer via Slack
                  </div>
                </div>
              </div>

            </div>

            {/* ── Unresolved banner (if any) ── */}
            {data.unresolved > 0 && (
              <div style={{
                padding:'10px 16px',background:'#fffbeb',border:'1px solid #fde68a',
                borderRadius:4,display:'flex',alignItems:'center',gap:10,
              }}>
                <div style={{width:6,height:6,borderRadius:'50%',background:'#D97706',flexShrink:0}}/>
                <span style={{fontFamily:'"IBM Plex Mono",monospace',fontSize:11,color:'#92400e',fontWeight:600}}>
                  {data.unresolved} tickets currently unresolved
                </span>
                <span style={{fontSize:11,color:'#92400e'}}>—</span>
                <span style={{fontSize:11,color:'#92400e'}}>{data.open} open · {data.in_progress} in progress</span>
              </div>
            )}

            {/* ── Volume chart + Priority ── */}
            <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:12}}>

              {/* Volume chart */}
              <div className="card">
                <div className="ch-head">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                  <h3>Ticket Volume · last 30 days</h3>
                  <div style={{flex:1}}/>
                  <div style={{display:'flex',gap:12}}>
                    {[
                      {c:'rgba(23,77,56,0.3)',l:'Created'},
                      {c:'#1a7a4a',l:'AI Solved'},
                      {c:'#D97706',l:'Routed'},
                    ].map((x,i) => (
                      <div key={i} style={{display:'flex',alignItems:'center',gap:4}}>
                        <div style={{width:10,height:10,background:x.c,borderRadius:2}}/>
                        <span className="tiny muted mono">{x.l}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{padding:'16px 16px 12px'}}>
                  <div style={{display:'flex',alignItems:'flex-end',gap:2,height:120}}>
                    {data.time_series.map((d,i) => (
                      <div key={i} style={{flex:1,display:'flex',flexDirection:'column',justifyContent:'flex-end',gap:1,height:'100%'}}>
                        <div title={`${d.label}: ${d.routed} routed`}
                          style={{background:'#D97706',borderRadius:'1px 1px 0 0',height:`${(d.routed/maxTime)*100}px`,minHeight:d.routed>0?2:0}}/>
                        <div title={`${d.label}: ${d.ai_solved} AI solved`}
                          style={{background:'#1a7a4a',borderRadius:'1px 1px 0 0',height:`${(d.ai_solved/maxTime)*100}px`,minHeight:d.ai_solved>0?2:0}}/>
                        <div title={`${d.label}: ${d.created} created`}
                          style={{background:'rgba(23,77,56,0.25)',borderRadius:'1px 1px 0 0',height:`${(d.created/maxTime)*100}px`,minHeight:d.created>0?2:0}}/>
                      </div>
                    ))}
                  </div>
                  <div style={{display:'flex',justifyContent:'space-between',marginTop:6}}>
                    {data.time_series.filter((_,i)=>i%5===0).map((d,i)=>(
                      <span key={i} className="tiny muted mono">{d.label}</span>
                    ))}
                    <span className="tiny muted mono">Now</span>
                  </div>
                </div>
              </div>

              {/* Priority */}
              <div className="card">
                <div className="ch-head">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  <h3>By Priority</h3>
                </div>
                <div style={{padding:'12px 16px',display:'flex',flexDirection:'column',gap:14}}>
                  {data.priorities.map(p => {
                    const tot = Math.max(data.priorities.reduce((s,x)=>s+x.total,0),1)
                    const pct = Math.round(p.total/tot*100)
                    return (
                      <div key={p.priority}>
                        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:5}}>
                          <span className={`pill ${pPill(p.priority)}`}>{p.priority}</span>
                          <div>
                            <span style={{fontFamily:'"IBM Plex Mono",monospace',fontSize:14,fontWeight:600}}>{p.total}</span>
                            <span className="tiny muted mono" style={{marginLeft:5}}>{pct}%</span>
                          </div>
                        </div>
                        <div className="bar-bg">
                          <div className="bar-fill" style={{width:`${pct}%`,background:pColor(p.priority)}}/>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>

            {/* ── Domain table + Recent tickets ── */}
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>

              {/* Domain */}
              <div className="card">
                <div className="ch-head">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                  <h3>By Domain</h3>
                </div>
                <table className="dt">
                  <thead>
                    <tr><th>Domain</th><th>Total</th><th>Open</th><th>Resolved</th><th style={{width:80}}>Load</th></tr>
                  </thead>
                  <tbody>
                    {data.domains.sort((a,b)=>b.total-a.total).map(d=>(
                      <tr key={d.domain}>
                        <td style={{fontWeight:500}}>{d.label}</td>
                        <td style={{fontFamily:'"IBM Plex Mono",monospace',fontWeight:600}}>{d.total}</td>
                        <td><span className="pill p-warn">{d.open}</span></td>
                        <td><span className="pill p-ok">{d.resolved}</span></td>
                        <td>
                          <div className="bar-bg">
                            <div className="bar-fill" style={{width:`${(d.total/maxDomain)*100}%`,background:'#174D38'}}/>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Recent tickets */}
              <div className="card">
                <div className="ch-head">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  <h3>Recent Tickets</h3>
                </div>
                <table className="dt">
                  <thead>
                    <tr><th>ID</th><th>Issue</th><th>Resolved by</th><th>Status</th><th>Priority</th></tr>
                  </thead>
                  <tbody>
                    {data.recent.map(t=>(
                      <tr key={t.ticket_number}>
                        <td style={{fontFamily:'"IBM Plex Mono",monospace',fontSize:11,color:'#174D38',fontWeight:600,whiteSpace:'nowrap'}}>
                          {t.ticket_number}
                        </td>
                        <td style={{maxWidth:130}}>
                          <div style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',fontSize:12}}>{t.title}</div>
                          <div className="tiny muted">{t.user_city||'—'}</div>
                        </td>
                        <td>
                          {t.ai_attempted && !t.engineer_name
                            ? <span className="pill p-ok">AI Bot</span>
                            : t.engineer_name
                            ? <span className="tiny" style={{color:'#555'}}>{t.engineer_name}</span>
                            : <span className="tiny muted">—</span>
                          }
                        </td>
                        <td><span className={`pill ${sPill(t.status)}`}>{t.status.replace('_',' ')}</span></td>
                        <td><span className={`pill ${pPill(t.priority)}`}>{t.priority}</span></td>
                      </tr>
                    ))}
                    {data.recent.length===0 && (
                      <tr><td colSpan={5} style={{textAlign:'center',padding:32,color:'#888',fontSize:12}}>No tickets yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

            </div>
          </>
        )}
      </div>
    </>
  )
}