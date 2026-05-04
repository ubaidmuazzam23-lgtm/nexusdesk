'use client'
// File: frontend/src/app/chat/page.tsx

import { useState, useEffect, useRef, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Message {
  role: 'user' | 'assistant'
  content: string
  canEscalate?: boolean
  resolved?: boolean
  imageUrl?: string
  cnnResult?: { cnn_label: string; cnn_confidence: number; cnn_domain: string; cnn_severity: string }
}
interface Ticket {
  id: string; ticket_number: string; title: string; domain: string
  priority: string; status: string; engineer_name: string; engineer_id: string
  engineer_city: string; engineer_country: string; engineer_timezone: string; created_at: string
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',other:'Other',
}[d] || d)

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{--bg:#f6f7f9;--bg-elev:#fff;--bg-sun:#f0f2f5;--fg:#0f1419;--fg-dim:#4a5568;--fg-mute:#7a8699;--fg-faint:#a4aebc;--brd:#e4e7ec;--brd-s:#cdd2db;--acc:#3b82f6;--acc-fg:#fff;--acc-w:#eff6ff;--acc-soft:#bfdbfe;--ok:#16a34a;--ok-w:#f0fdf4;--warn:#d97706;--warn-w:#fffbeb;--crit:#dc2626;--crit-w:#fef2f2;--pur:#7c3aed;--pur-w:#f5f3ff}
.ch *{box-sizing:border-box;margin:0;padding:0}
.ch{font-family:"Inter",-apple-system,sans-serif;font-size:13px;line-height:1.45;color:var(--fg);background:var(--bg);height:100vh;display:grid;grid-template-columns:220px 1fr;overflow:hidden;-webkit-font-smoothing:antialiased}
.ch .sidebar{background:var(--bg-elev);border-right:1px solid var(--brd);display:flex;flex-direction:column;overflow:hidden}
.ch .sb-head{height:48px;padding:0 14px;display:flex;align-items:center;gap:9px;border-bottom:1px solid var(--brd);flex-shrink:0}
.ch .logomark{width:22px;height:22px;border-radius:5px;background:var(--fg);color:var(--bg-elev);display:grid;place-items:center;font-family:"JetBrains Mono",monospace;font-weight:700;font-size:11px;flex-shrink:0}
.ch .nav-lbl{padding:8px 14px 3px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-faint);font-weight:600;font-family:"JetBrains Mono",monospace}
.ch .nav-item{display:flex;align-items:center;gap:10px;padding:6px 14px;height:30px;font-size:13px;color:var(--fg-dim);cursor:pointer;border-left:2px solid transparent;user-select:none;transition:background .1s}
.ch .nav-item:hover{background:var(--bg-sun);color:var(--fg)}
.ch .nav-item.active{background:var(--acc-w);color:var(--acc);border-left-color:var(--acc);font-weight:500}
.ch .nav-badge{margin-left:auto;font-family:"JetBrains Mono",monospace;font-size:10px;color:var(--fg-faint)}
.ch .nav-item.active .nav-badge{color:var(--acc)}
.ch .sb-foot{margin-top:auto;border-top:1px solid var(--brd);padding:10px 14px;display:flex;align-items:center;gap:9px}
.ch .main{display:grid;grid-template-rows:48px 1fr;overflow:hidden}
.ch .topbar{height:48px;background:var(--bg-elev);border-bottom:1px solid var(--brd);display:flex;align-items:center;padding:0 14px;gap:12px;flex-shrink:0}
.ch .chat-shell{display:grid;grid-template-rows:1fr auto;height:100%;overflow:hidden}
.ch .chat-scroll{overflow-y:auto;padding:20px 0 12px}
.ch .chat-wrap{max-width:760px;margin:0 auto;padding:0 24px;display:flex;flex-direction:column;gap:14px}
.ch .msg{display:flex;gap:10px;align-items:flex-start}
.ch .msg-u{justify-content:flex-end}
.ch .msg-av{width:26px;height:26px;border-radius:5px;background:var(--fg);color:var(--bg-elev);display:grid;place-items:center;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:700;flex-shrink:0;margin-top:2px}
.ch .bubble{max-width:600px;background:var(--bg-elev);border:1px solid var(--brd);border-radius:6px;padding:9px 13px;font-size:13px;line-height:1.55;color:var(--fg)}
.ch .bubble-u{background:var(--acc)!important;color:var(--acc-fg)!important;border-color:var(--acc)!important}
.ch .chat-card{background:var(--bg-elev);border:1px solid var(--brd);border-radius:6px;overflow:hidden;max-width:580px}
.ch .cc-head{padding:7px 12px;border-bottom:1px solid var(--brd);background:var(--bg-sun);display:flex;align-items:center;gap:8px;font-size:10px;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--fg-mute);font-weight:600}
.ch .chat-bar{border-top:1px solid var(--brd);background:var(--bg-elev);padding:12px 24px 16px;flex-shrink:0}
.ch .chat-input{max-width:760px;margin:0 auto;background:var(--bg-elev);border:1px solid var(--brd-s);border-radius:6px;padding:8px 10px 8px 13px;display:flex;align-items:flex-end;gap:8px;transition:border-color .15s}
.ch .chat-input:focus-within{border-color:var(--acc);box-shadow:0 0 0 3px var(--acc-w)}
.ch .chat-input textarea{all:unset;flex:1;font-family:inherit;font-size:13px;color:var(--fg);min-height:20px;max-height:120px;resize:none;line-height:1.5}
.ch .chat-input textarea::placeholder{color:var(--fg-faint)}
.ch .send-btn{width:30px;height:30px;border-radius:4px;background:var(--fg);color:var(--bg-elev);display:grid;place-items:center;cursor:pointer;border:none;flex-shrink:0;transition:opacity .1s}
.ch .send-btn:disabled{opacity:.3;cursor:not-allowed}
.ch .ic{background:var(--bg-elev);border:1px solid var(--brd);border-radius:6px;padding:14px;cursor:pointer;transition:all .12s}
.ch .ic:hover{border-color:var(--fg);transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,20,25,.07)}
.ch .ic-icon{width:28px;height:28px;border-radius:6px;background:var(--bg-sun);display:grid;place-items:center;color:var(--fg-dim);margin-bottom:10px}
.ch .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:var(--bg-sun);color:var(--fg-dim);border:1px solid var(--brd);white-space:nowrap}
.ch .pill-ok{background:var(--ok-w);color:var(--ok);border-color:transparent}
.ch .pill-warn{background:var(--warn-w);color:var(--warn);border-color:transparent}
.ch .pill-crit{background:var(--crit-w);color:var(--crit);border-color:transparent}
.ch .pill-acc{background:var(--acc-w);color:var(--acc);border-color:transparent}
.ch .pill-pur{background:var(--pur-w);color:var(--pur);border-color:transparent}
.ch .cnn-card{margin-top:8px;padding:10px 12px;background:var(--ok-w);border:1px solid #bbf7d0;border-radius:6px}
.ch .cnn-label{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--ok);font-weight:700;font-family:"JetBrains Mono",monospace;margin-bottom:5px}
.ch .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--fg-faint)}
.ch .dot-ok{background:var(--ok)}.ch .dot-acc{background:var(--acc)}
.ch .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid var(--brd);background:var(--bg-elev);color:var(--fg);font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
.ch .btn:hover{background:var(--bg-sun)}
.ch .btn-p{background:var(--fg)!important;color:var(--bg-elev)!important;border-color:var(--fg)!important}
.ch .btn-a{background:var(--acc)!important;color:var(--acc-fg)!important;border-color:var(--acc)!important}
.ch .btn-sm{height:24px;padding:0 8px;font-size:11px}
.ch .thinking{display:inline-flex;gap:3px;align-items:center}
.ch .thinking span{width:5px;height:5px;border-radius:50%;background:var(--fg-mute);animation:think 1.2s ease-in-out infinite}
.ch .thinking span:nth-child(2){animation-delay:.15s}
.ch .thinking span:nth-child(3){animation-delay:.3s}
@keyframes think{0%,80%,100%{transform:scale(.6);opacity:.4}40%{transform:scale(1);opacity:1}}
.ch .fade{animation:fade .35s ease-out both}
@keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.ch .mono{font-family:"JetBrains Mono",monospace}
.ch .muted{color:var(--fg-mute)}
.ch .small{font-size:11px}
.ch .tiny{font-size:10px}
.ch .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--brd);border-radius:3px}
`

function Thinking() {
  return (
    <div className="msg fade">
      <div className="msg-av">AI</div>
      <div className="bubble">
        <div className="thinking"><span /><span /><span /></div>
      </div>
    </div>
  )
}

function LiveClock({ tz }: { tz: string }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i) }, [])
  try { return <span>{now.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', hour12: true })}</span> }
  catch { return <span>—</span> }
}

export default function ChatPage() {
  const [view, setView]               = useState<'chat' | 'tickets'>('chat')
  const [messages, setMessages]       = useState<Message[]>([])
  const [input, setInput]             = useState('')
  const [loading, setLoading]         = useState(false)
  const [uploading, setUploading]     = useState(false)
  const [sessionId, setSessionId]     = useState<string | null>(null)
  const [intent, setIntent]           = useState<'solve' | 'service_request' | null>(null)
  const [canEscalate, setCanEscalate] = useState(false)
  const [showEscalate, setShowEscalate] = useState(false)
  const [escalating, setEscalating]   = useState(false)
  const [lastDomain, setLastDomain]   = useState('other')
  const [lastSeverity, setLastSeverity] = useState('medium')
  const [fullName, setFullName]       = useState('there')
  const [tickets, setTickets]         = useState<Ticket[]>([])
  const [escalateForm, setEscalateForm] = useState({ title: '', description: '', steps_tried: '' })
  const [mounted, setMounted]         = useState(false)
  const [imgPreview, setImgPreview]   = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textRef   = useRef<HTMLTextAreaElement>(null)
  const fileRef   = useRef<HTMLInputElement>(null)

  const token = () => localStorage.getItem('access_token') || ''
  const hdrs  = useCallback(() => ({ Authorization: `Bearer ${token()}` }), [])

  useEffect(() => {
    setMounted(true)
    const name = localStorage.getItem('full_name')
    const role = localStorage.getItem('role')
    if (role !== 'user') window.location.replace('/auth/login')
    if (name) setFullName(name.split(' ')[0])
    fetchTickets()
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading, uploading])

  const fetchTickets = async () => {
    try {
      const r = await fetch(`${API}/api/v1/chat/tickets`, { headers: hdrs() })
      if (r.ok) setTickets(await r.json())
    } catch {}
  }

  const ensureSession = () => {
    if (sessionId) return sessionId
    const id = crypto.randomUUID()
    setSessionId(id)
    return id
  }

  const startChat = (sel: 'solve' | 'service_request') => {
    setIntent(sel)
    setMessages([{ role: 'assistant', content: sel === 'service_request'
      ? "Sure — tell me what you need. I can help with software installations, hardware requests, access setup, or any other IT service."
      : "I'm here to help. Describe your issue or upload a screenshot and I will diagnose it." }])
    setTimeout(() => textRef.current?.focus(), 100)
  }

  const sendMessage = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    const sid = ensureSession()
    setInput('')
    setImgPreview(null)
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/v1/chat/message`, {
        method: 'POST', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, session_id: sid, intent }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error()
      if (!sessionId) setSessionId(d.session_id)
      if (d.detected_domain && d.detected_domain !== 'other') setLastDomain(d.detected_domain)
      if (d.detected_severity) setLastSeverity(d.detected_severity)
      setMessages(prev => [...prev, { role: 'assistant', content: d.reply, canEscalate: d.can_escalate, resolved: d.resolved }])
      setCanEscalate(d.can_escalate)
      if (d.can_escalate) {
        setEscalateForm({
          title: `${dLabel(d.detected_domain || lastDomain)} issue — ${new Date().toLocaleDateString()}`,
          description: messages.filter(m => m.role === 'user').map(m => m.content).join('\n') + '\n' + msg,
          steps_tried: '',
        })
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }])
    } finally { setLoading(false) }
  }

  // ── Screenshot upload → CNN ────────────────────────────────────────────────
  const handleScreenshot = async (file: File) => {
    if (!file) return
    const sid = ensureSession()
    setUploading(true)
    // Show preview immediately
    const preview = await new Promise<string>(resolve => {
      const r = new FileReader()
      r.onload = e => resolve(e.target?.result as string)
      r.readAsDataURL(file)
    })
    setMessages(prev => [...prev, { role: 'user', content: '', imageUrl: preview }])
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('session_id', sid)
      const r = await fetch(`${API}/api/v1/chat/upload-screenshot`, {
        method: 'POST', headers: hdrs(), body: fd
      })
      const d = await r.json()
      if (!r.ok || !d.success) throw new Error(d.error || 'Upload failed')
      if (d.cnn_domain && d.cnn_domain !== 'other') setLastDomain(d.cnn_domain)
      if (d.cnn_severity) setLastSeverity(d.cnn_severity)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: d.display_text,
        cnnResult: {
          cnn_label: d.cnn_label,
          cnn_confidence: d.cnn_confidence,
          cnn_domain: d.cnn_domain,
          cnn_severity: d.cnn_severity,
        }
      }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Could not analyze the screenshot. Please describe what you are seeing.' }])
    } finally { setUploading(false) }
  }

  const handleEscalate = async () => {
    if (!escalateForm.title || !escalateForm.description) return
    setEscalating(true)
    try {
      const r = await fetch(`${API}/api/v1/chat/escalate`, {
        method: 'POST', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId, title: escalateForm.title,
          description: escalateForm.description, domain: lastDomain,
          priority: lastSeverity === 'critical' ? 'critical' : lastSeverity === 'high' ? 'high' : 'medium',
          steps_tried: escalateForm.steps_tried
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail)
      setMessages(prev => [...prev, { role: 'assistant', content: `✓ Ticket ${d.ticket_number} raised and routed to the best available engineer.` }])
      setShowEscalate(false); setCanEscalate(false); setSessionId(null); setIntent(null)
      fetchTickets()
    } catch (e: any) { alert(e.message) }
    finally { setEscalating(false) }
  }

  const resetChat = () => {
    setMessages([]); setIntent(null); setSessionId(null)
    setCanEscalate(false); setShowEscalate(false); setInput(''); setImgPreview(null)
  }

  const pPill = (p: string) => p === 'critical' ? 'pill-crit' : p === 'high' ? 'pill-warn' : p === 'medium' ? 'pill-acc' : ''
  const sPill = (s: string) => s === 'resolved' ? 'pill-ok' : s === 'in_progress' ? 'pill-warn' : s === 'open' ? 'pill-acc' : ''
  const openCount = tickets.filter(t => t.status !== 'resolved').length

  const sevColor = (s: string) => s === 'critical' ? 'var(--crit)' : s === 'high' ? 'var(--warn)' : s === 'medium' ? 'var(--acc)' : 'var(--ok)'

  if (!mounted) return null

  return (
    <>
      <style>{CSS}</style>
      <div className="ch">

        {/* Sidebar */}
        <div className="sidebar">
          <div className="sb-head">
            <div className="logomark">N</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: '-.01em' }}>NexusDesk</div>
              <div style={{ fontSize: 10, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.05em' }}>Support</div>
            </div>
          </div>
          <div className="nav-lbl">Support</div>
          {[
            { id: 'chat',    l: 'AI Chat',    badge: null },
            { id: 'tickets', l: 'My Tickets', badge: openCount > 0 ? openCount : null },
          ].map(n => (
            <div key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} onClick={() => setView(n.id as any)}>
              {n.id === 'chat'
                ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>
                : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3v4M8 3v4M2 13h20"/></svg>}
              {n.l}
              {n.badge !== null && <span className="nav-badge">{n.badge}</span>}
            </div>
          ))}
          <div className="sb-foot">
            <div style={{ width: 26, height: 26, borderRadius: 4, background: 'var(--acc)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{fullName.charAt(0).toUpperCase()}</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500 }}>{fullName}</div>
              <div style={{ fontSize: 10, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.05em' }}>User</div>
            </div>
            <button onClick={() => { localStorage.clear(); window.location.replace('/auth/login') }} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--fg-mute)', cursor: 'pointer', fontSize: 11 }}>Sign out</button>
          </div>
        </div>

        {/* Main */}
        <div className="main">
          <div className="topbar">
            <div style={{ fontSize: 12, color: 'var(--fg-mute)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>NexusDesk</span><span style={{ color: 'var(--fg-faint)' }}>/</span>
              <b style={{ color: 'var(--fg)', fontWeight: 500 }}>{view === 'chat' ? 'AI Chat' : 'My Tickets'}</b>
            </div>
            <span style={{ flex: 1 }} />
            <span className="dot dot-ok" />
            <span style={{ fontSize: 11, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace' }}>Claude AI · CNN Online</span>
          </div>

          {/* ── CHAT VIEW ── */}
          {view === 'chat' && (
            <div className="chat-shell">
              <div className="chat-scroll">
                <div className="chat-wrap">

                  {/* Intent selector */}
                  {!intent && messages.length === 0 && (
                    <div className="fade" style={{ paddingTop: 32 }}>
                      <div style={{ textAlign: 'center', marginBottom: 32 }}>
                        <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--fg)', display: 'grid', placeItems: 'center', margin: '0 auto 14px' }}>
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--bg-elev)" strokeWidth="1.8"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z"/></svg>
                        </div>
                        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-.02em', marginBottom: 6 }}>How can I help, {fullName}?</div>
                        <div style={{ fontSize: 13, color: 'var(--fg-mute)', maxWidth: 420, margin: '0 auto', lineHeight: 1.6 }}>Describe your issue or upload a screenshot. I'll diagnose it and guide you through a fix, or route it to the right engineer.</div>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, maxWidth: 580, margin: '0 auto' }}>
                        {[
                          { intent: 'solve' as const, icon: '🔧', title: 'Solve a Problem', sub: 'AI-powered diagnosis with CNN screenshot analysis. Step-by-step guided resolution.', tag: 'AI + CNN' },
                          { intent: 'service_request' as const, icon: '📋', title: 'Service Request', sub: 'Request software, hardware, access setup, or other IT services.', tag: 'Request' },
                        ].map(o => (
                          <div key={o.intent} className="ic" onClick={() => startChat(o.intent)}>
                            <div className="ic-icon" style={{ fontSize: 16 }}>{o.icon}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                              <div style={{ fontSize: 13, fontWeight: 600 }}>{o.title}</div>
                              <span style={{ fontSize: 9, padding: '1px 6px', background: 'var(--acc-w)', color: 'var(--acc)', borderRadius: 3, fontWeight: 700, fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em' }}>{o.tag}</span>
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--fg-mute)', lineHeight: 1.5 }}>{o.sub}</div>
                            <div style={{ marginTop: 12, fontSize: 11, color: 'var(--acc)', fontWeight: 500 }}>Get started →</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Messages */}
                  {messages.map((msg, i) => (
                    <div key={i}>
                      {msg.role === 'user' ? (
                        <div className="msg msg-u fade">
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, maxWidth: 600 }}>
                            {msg.imageUrl && (
                              <img src={msg.imageUrl} alt="screenshot" style={{ maxWidth: 300, borderRadius: 6, border: '1px solid var(--brd)' }} />
                            )}
                            {msg.content && <div className="bubble bubble-u">{msg.content}</div>}
                          </div>
                        </div>
                      ) : (
                        <div className="msg fade">
                          <div className="msg-av">AI</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 600 }}>
                            {msg.content && <div className="bubble" style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>}

                            {/* CNN Result card */}
                            {msg.cnnResult && msg.cnnResult.cnn_confidence > 0 && (
                              <div className="cnn-card">
                                <div className="cnn-label">🤖 CNN Detection Result</div>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{msg.cnnResult.cnn_label}</div>
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                  <span style={{ fontSize: 10, padding: '2px 8px', background: sevColor(msg.cnnResult.cnn_severity) + '18', color: sevColor(msg.cnnResult.cnn_severity), borderRadius: 3, fontWeight: 700, textTransform: 'uppercase', fontFamily: '"JetBrains Mono",monospace' }}>{msg.cnnResult.cnn_severity}</span>
                                  <span style={{ fontSize: 10, padding: '2px 8px', background: 'var(--bg-sun)', color: 'var(--fg-mute)', borderRadius: 3, fontFamily: '"JetBrains Mono",monospace' }}>{msg.cnnResult.cnn_domain?.replace(/_/g, ' ')}</span>
                                  <span style={{ fontSize: 10, padding: '2px 8px', background: 'var(--ok-w)', color: 'var(--ok)', borderRadius: 3, fontFamily: '"JetBrains Mono",monospace', fontWeight: 600 }}>{Math.round(msg.cnnResult.cnn_confidence * 100)}% confidence</span>
                                </div>
                              </div>
                            )}

                            {msg.canEscalate && !showEscalate && (
                              <button className="btn btn-a btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setShowEscalate(true)}>
                                Raise Support Ticket →
                              </button>
                            )}
                            {msg.resolved && (
                              <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }} onClick={resetChat}>Start New Chat</button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  {(loading || uploading) && <Thinking />}

                  {/* Escalate form */}
                  {showEscalate && (
                    <div className="fade">
                      <div className="chat-card" style={{ maxWidth: 580 }}>
                        <div className="cc-head" style={{ background: 'var(--crit-w)', color: 'var(--crit)' }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                          ESCALATION PACKAGE
                        </div>
                        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                          {[
                            { l: 'Title', k: 'title', type: 'input' },
                            { l: 'Description', k: 'description', type: 'textarea' },
                            { l: 'Steps Already Tried', k: 'steps_tried', type: 'textarea', ph: 'What have you already attempted?' },
                          ].map(f => (
                            <div key={f.k}>
                              <div style={{ fontSize: 10, fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--fg-mute)', marginBottom: 4 }}>{f.l}</div>
                              {f.type === 'input'
                                ? <input value={(escalateForm as any)[f.k]} onChange={e => setEscalateForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ all: 'unset', width: '100%', boxSizing: 'border-box', padding: '6px 10px', background: 'var(--bg-sun)', border: '1px solid var(--brd-s)', borderRadius: 4, fontFamily: 'inherit', fontSize: 13, color: 'var(--fg)' }} />
                                : <textarea rows={3} placeholder={(f as any).ph} value={(escalateForm as any)[f.k]} onChange={e => setEscalateForm(p => ({ ...p, [f.k]: e.target.value }))} style={{ all: 'unset', width: '100%', boxSizing: 'border-box', padding: '6px 10px', background: 'var(--bg-sun)', border: '1px solid var(--brd-s)', borderRadius: 4, fontFamily: 'inherit', fontSize: 13, color: 'var(--fg)', minHeight: 64, resize: 'vertical', display: 'block' }} />}
                            </div>
                          ))}
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button className="btn btn-sm" onClick={() => setShowEscalate(false)}>Cancel</button>
                            <button className="btn btn-a btn-sm" disabled={escalating} onClick={handleEscalate}>
                              {escalating ? 'Raising ticket…' : '✓ Raise Support Ticket'}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Input bar */}
              {intent && !showEscalate && (
                <div className="chat-bar">
                  <div className="chat-input">
                    <textarea
                      ref={textRef}
                      rows={1}
                      placeholder="Describe your issue…"
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                      disabled={loading || uploading}
                    />
                    <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
                      onChange={e => { const f = e.target.files?.[0]; if (f) handleScreenshot(f); e.target.value = '' }} />
                    {/* Screenshot upload button */}
                    <button
                      style={{ width: 30, height: 30, borderRadius: 4, background: 'var(--bg-sun)', border: '1px solid var(--brd)', display: 'grid', placeItems: 'center', cursor: 'pointer', flexShrink: 0, color: 'var(--fg-mute)' }}
                      onClick={() => fileRef.current?.click()}
                      disabled={uploading}
                      title="Upload screenshot for CNN analysis"
                    >
                      {uploading
                        ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'spin 1s linear infinite' }}><circle cx="12" cy="12" r="10"/></svg>
                        : <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                      }
                    </button>
                    <button className="send-btn" disabled={loading || uploading || !input.trim()} onClick={sendMessage}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                    </button>
                  </div>
                  <div style={{ maxWidth: 760, margin: '6px auto 0', display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 11, color: 'var(--fg-faint)', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                      Upload screenshot for instant CNN detection
                    </span>
                    <button style={{ fontSize: 11, color: 'var(--fg-mute)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }} onClick={resetChat}>New Chat</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── TICKETS VIEW ── */}
          {view === 'tickets' && (
            <div style={{ overflow: 'auto', padding: 16 }}>
              <div style={{ maxWidth: 900, margin: '0 auto' }}>
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-.01em' }}>My Tickets</div>
                  <div className="small muted">All support requests you have raised</div>
                </div>
                <div style={{ background: 'var(--bg-elev)', border: '1px solid var(--brd)', borderRadius: 6 }}>
                  {tickets.length === 0 ? (
                    <div style={{ padding: '48px 24px', textAlign: 'center' }}>
                      <div style={{ fontSize: 28, marginBottom: 12 }}>◈</div>
                      <div style={{ fontWeight: 600, marginBottom: 6 }}>No tickets yet</div>
                      <div className="small muted" style={{ marginBottom: 16 }}>Start a chat to raise your first support ticket.</div>
                      <button className="btn btn-p btn-sm" onClick={() => setView('chat')}>Start Chat →</button>
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr>
                          {['ID', 'Issue', 'Priority', 'Status', 'Engineer', 'Created'].map(h => (
                            <th key={h} style={{ textAlign: 'left', fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--fg-mute)', padding: '8px 12px', background: 'var(--bg-sun)', borderBottom: '1px solid var(--brd)', fontWeight: 600, fontFamily: '"JetBrains Mono",monospace', whiteSpace: 'nowrap' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tickets.map(t => (
                          <tr key={t.id} style={{ borderBottom: '1px solid var(--bg-sun)' }}>
                            <td style={{ padding: '10px 12px' }}><span className="mono" style={{ color: 'var(--acc)', fontWeight: 600, fontSize: 11 }}>{t.ticket_number}</span></td>
                            <td style={{ padding: '10px 12px', maxWidth: 280 }}><div className="trunc" style={{ fontWeight: 500 }}>{t.title}</div></td>
                            <td style={{ padding: '10px 12px' }}><span className={`pill ${pPill(t.priority)}`}>{t.priority}</span></td>
                            <td style={{ padding: '10px 12px' }}><span className={`pill ${sPill(t.status)}`}>{t.status.replace('_', ' ')}</span></td>
                            <td style={{ padding: '10px 12px' }}>
                              {t.engineer_name ? (
                                <div>
                                  <div style={{ fontWeight: 500, fontSize: 12 }}>{t.engineer_name}</div>
                                  {t.engineer_city && (
                                    <div className="tiny muted">{t.engineer_city} · {t.engineer_timezone && <LiveClock tz={t.engineer_timezone} />} local</div>
                                  )}
                                </div>
                              ) : <span className="muted">—</span>}
                            </td>
                            <td style={{ padding: '10px 12px' }}>
                              <span className="small muted mono">{new Date(t.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}