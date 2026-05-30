'use client'
// File: frontend/src/app/engineer/dashboard/page.tsx
import { useState, useEffect, useCallback, useRef } from 'react'

const API    = process.env.NEXT_PUBLIC_API_URL
const WS_URL = process.env.NEXT_PUBLIC_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'

interface Ticket {
  id: string; ticket_number: string; title: string; description: string
  domain: string; priority: string; status: string; complexity: string
  ai_diagnosis: string; steps_tried: string; resolution_notes: string
  cnn_image_result: string; sla_deadline: string; sla_breached: boolean
  user_name: string; user_email: string; user_city: string
  user_country: string; user_timezone: string; created_at: string
}
interface Stats {
  total_resolved: number; active_tickets: number
  avg_resolution_time: number; sla_compliance_rate: number; this_week_resolved: number
}
interface KBResult {
  content: string; title: string; doc_id: string
  domain: string; cosine_similarity: number; filename: string
}
interface TeamInfo {
  team_id: string; name: string; domain_focus: string[]
  region: string; timezone: string
  manager_name: string; manager_email: string
  member_count: number; role_in_team: string
}
interface ChatMessage {
  id: string; message: string; sender_id: string
  sender_name: string; sender_role: string
  timestamp: string; type?: 'message' | 'system'; online_count?: number
}

const pPill = (p: string) =>
  p === 'critical' ? 'pill-crit' : p === 'high' ? 'pill-warn' : p === 'medium' ? 'pill-grn' : ''
const sPill = (s: string) =>
  s === 'resolved' ? 'pill-ok' : s === 'in_progress' ? 'pill-grn' : s === 'open' ? 'pill-warn' : ''
const dLabel = (d: string) => ({
  networking: 'Networking', hardware: 'Hardware', software: 'Software',
  security: 'Security', email_communication: 'Email & Comm',
  identity_access: 'Identity & Access', database: 'Database', cloud: 'Cloud',
  infrastructure: 'Infrastructure', devops: 'DevOps',
  erp_business_apps: 'ERP & Business', endpoint_management: 'Endpoint Mgmt', other: 'Other',
}[d] || d)
const simColor = (s: number) => s >= 80 ? 'var(--ok)' : s >= 60 ? 'var(--warn)' : s >= 40 ? '#2a6bab' : 'var(--fg-mute)'
const simLabel = (s: number) => s >= 80 ? 'High' : s >= 60 ? 'Good' : s >= 40 ? 'Fair' : 'Low'

function LiveClock({ tz, label }: { tz: string; label: string }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i) }, [])
  const time = (() => { try { return now.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) } catch { return '--:--:--' } })()
  const date = (() => { try { return now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric' }) } catch { return '' } })()
  return (
    <div style={{ textAlign: 'center', minWidth: 140 }}>
      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--fg-mute)', marginBottom: 2, fontFamily: '"JetBrains Mono",monospace' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, fontFamily: '"JetBrains Mono",monospace', color: 'var(--fg)', fontVariantNumeric: 'tabular-nums', letterSpacing: '-.01em' }}>{time}</div>
      <div style={{ fontSize: 10, color: 'var(--fg-mute)', marginTop: 2 }}>{date} · {tz}</div>
    </div>
  )
}

function ScreenshotImage({ url }: { url: string }) {
  const [src, setSrc]     = useState<string | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  useEffect(() => {
    let rev = ''; setState('loading'); setSrc(null)
    const token = localStorage.getItem('access_token')
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => { if (!r.ok) throw new Error(); return r.blob() })
      .then(b => { rev = URL.createObjectURL(b); setSrc(rev); setState('ready') })
      .catch(() => setState('error'))
    return () => { if (rev) URL.revokeObjectURL(rev) }
  }, [url])
  if (state === 'loading') return <div className="kb-c" style={{ textAlign: 'center' }}>Loading screenshot...</div>
  if (state === 'error' || !src) return <div className="kb-c" style={{ textAlign: 'center', color: 'var(--crit)' }}>Screenshot unavailable</div>
  return <img src={src} alt="screenshot" style={{ width: '100%', borderRadius: 4, border: '1px solid var(--brd)', maxHeight: 220, objectFit: 'contain', background: 'var(--bg)' }} />
}

export default function EngineerDashboardPage() {
  const [tickets,    setTickets]    = useState<Ticket[]>([])
  const [stats,      setStats]      = useState<Stats | null>(null)
  const [teamInfo,   setTeamInfo]   = useState<TeamInfo | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [theme,      setTheme]      = useState('light')
  const [selected,   setSelected]   = useState<Ticket | null>(null)
  const [tab,        setTab]        = useState<'queue' | 'kb' | 'history' | 'chat'>('queue')
  const [updating,   setUpdating]   = useState(false)
  const [notes,      setNotes]      = useState('')
  const [engTz,      setEngTz]      = useState('UTC')
  const [engName,    setEngName]    = useState('')
  const [engId,      setEngId]      = useState('')
  const [availability, setAvailability] = useState('available')
  const [mounted,    setMounted]    = useState(false)
  const [kbResults,  setKbResults]  = useState<KBResult[]>([])
  const [kbLoading,  setKbLoading]  = useState(false)
  const [kbExpanded, setKbExpanded] = useState<number | null>(null)
  const [kbSearch,   setKbSearch]   = useState('')
  const [kbSearchRes, setKbSearchRes] = useState<KBResult[]>([])
  const [kbSearching, setKbSearching] = useState(false)
  const [toast,      setToast]      = useState<{ title: string; desc: string; type: string } | null>(null)

  // Chat state
  const [chatMessages,  setChatMessages]  = useState<ChatMessage[]>([])
  const [chatInput,     setChatInput]     = useState('')
  const [chatConnected, setChatConnected] = useState(false)
  const [onlineCount,   setOnlineCount]   = useState(0)
  const wsRef      = useRef<WebSocket | null>(null)
  const chatBottom = useRef<HTMLDivElement>(null)
  const currentUserId = typeof window !== 'undefined' ? localStorage.getItem('user_id') || '' : ''

  const token = () => localStorage.getItem('access_token') || ''
  const hdrs  = useCallback(() => ({ Authorization: `Bearer ${token()}` }), [])

  useEffect(() => {
    const saved = localStorage.getItem('eng_theme') || 'light'
    setTheme(saved)
    document.documentElement.setAttribute('data-theme', saved)
    setMounted(true)
    fetchProfile(); fetchData(); fetchTeamInfo()
    const i = setInterval(fetchData, 30000)
    return () => clearInterval(i)
  }, [])

  useEffect(() => {
    if (selected) fetchKB(selected)
    else setKbResults([])
  }, [selected])

  // Connect/disconnect chat when switching to chat tab
  useEffect(() => {
    if (tab === 'chat' && teamInfo?.team_id) {
      connectChat(teamInfo.team_id)
    } else {
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
      setChatConnected(false)
    }
    return () => {
      if (tab !== 'chat' && wsRef.current) { wsRef.current.close(); wsRef.current = null }
    }
  }, [tab, teamInfo?.team_id])

  useEffect(() => {
    chatBottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    localStorage.setItem('eng_theme', next)
    document.documentElement.setAttribute('data-theme', next)
  }

  const showToast = (title: string, desc: string, type = 'ok') => {
    setToast({ title, desc, type })
    setTimeout(() => setToast(null), 4500)
  }

  const fetchProfile = async () => {
    try {
      const r = await fetch(`${API}/api/v1/engineer/profile`, { headers: hdrs() })
      if (r.status === 401) { localStorage.clear(); window.location.replace('/auth/login'); return }
      if (r.ok) {
        const d = await r.json()
        setEngTz(d.timezone || 'UTC')
        setEngName(d.full_name || '')
        setEngId(d.engineer_id || '')
        setAvailability(d.availability_status || 'available')
      }
    } catch {}
  }

  const fetchData = async () => {
    try {
      const [tR, sR] = await Promise.all([
        fetch(`${API}/api/v1/engineer/tickets`, { headers: hdrs() }),
        fetch(`${API}/api/v1/engineer/stats`, { headers: hdrs() }),
      ])
      if (tR.status === 401) { localStorage.clear(); window.location.replace('/auth/login'); return }
      if (tR.ok) setTickets(await tR.json())
      if (sR.ok) setStats(await sR.json())
    } catch {} finally { setLoading(false) }
  }

  const fetchTeamInfo = async () => {
    try {
      const r = await fetch(`${API}/api/v1/engineer/my-team`, { headers: hdrs() })
      if (r.ok) setTeamInfo(await r.json())
    } catch {}
  }

  const connectChat = async (teamId: string) => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    setChatMessages([]); setChatConnected(false)

    // Load history
    try {
      const r = await fetch(`${API}/api/v1/teams/${teamId}/chat`, { headers: hdrs() })
      if (r.ok) {
        const history = await r.json()
        setChatMessages(history.map((m: any) => ({ ...m, type: 'message' })))
      }
    } catch {}

    const tk = localStorage.getItem('access_token') || ''
    const ws = new WebSocket(`${WS_URL}/api/v1/teams/${teamId}/ws?token=${tk}`)
    ws.onopen    = () => setChatConnected(true)
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.online_count !== undefined) setOnlineCount(msg.online_count)
        setChatMessages(prev => [...prev, msg])
      } catch {}
    }
    ws.onclose  = () => setChatConnected(false)
    ws.onerror  = () => setChatConnected(false)
    wsRef.current = ws
  }

  const sendChatMessage = () => {
    if (!chatInput.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(chatInput.trim())
    setChatInput('')
  }

  const handleChatKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage() }
  }

  const fetchKB = async (ticket: Ticket) => {
    setKbLoading(true); setKbResults([])
    try {
      const r = await fetch(`${API}/api/v1/knowledge/ticket-similarity/${ticket.id}`, { headers: hdrs() })
      if (r.ok) { const d = await r.json(); setKbResults(d.results || []) }
    } catch {} finally { setKbLoading(false) }
  }

  const setAvail = async (s: string) => {
    try {
      await fetch(`${API}/api/v1/engineer/availability`, {
        method: 'PATCH', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ availability_status: s }),
      })
      setAvailability(s)
    } catch {}
  }

  const resolveTicket = async () => {
    if (!selected || !notes.trim()) return
    setUpdating(true)
    try {
      const r = await fetch(`${API}/api/v1/engineer/tickets/${selected.id}/resolve`, {
        method: 'PATCH', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolution_notes: notes }),
      })
      if (r.ok) {
        fetchData(); setSelected(null); setNotes('')
        showToast('Ticket resolved', 'Resolution notes indexed to KB.', 'ok')
      }
    } catch {} finally { setUpdating(false) }
  }

  const markInProgress = async () => {
    if (!selected) return
    try {
      await fetch(`${API}/api/v1/engineer/tickets/${selected.id}/status`, {
        method: 'PATCH', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'in_progress' }),
      })
      fetchData()
    } catch {}
  }

  const searchKB = async () => {
    if (!kbSearch.trim()) return
    setKbSearching(true); setKbSearchRes([])
    try {
      const r = await fetch(`${API}/api/v1/knowledge/search`, {
        method: 'POST', headers: { ...hdrs(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: kbSearch, n_results: 8 }),
      })
      if (r.ok) { const d = await r.json(); setKbSearchRes(d.results || []) }
    } catch {} finally { setKbSearching(false) }
  }

  const getScreenshotUrl = (cnn: string | null) => {
    if (!cnn) return null
    const f = cnn.split(' |')[0].trim()
    if (!f.match(/\.(png|jpg|jpeg|webp)$/i)) return null
    return `${API}/api/v1/chat/screenshot/${f}`
  }

  const fmtTime = (iso: string, tz?: string) => {
    try {
      return new Date(iso).toLocaleString('en-US', {
        timeZone: tz || 'UTC', month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
      })
    } catch { return iso }
  }

  const chatTime = (s: string) =>
    new Date(s).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })

  const roleColor = (role: string) => {
    if (role === 'manager') return '#5b3d8a'
    if (role === 'admin')   return 'var(--crit)'
    return 'var(--grn)'
  }

  const getBubbleClass = (msg: ChatMessage) => {
    if (msg.type === 'system')           return 'system'
    if (msg.sender_id === currentUserId) return 'mine'
    if (msg.sender_role === 'manager')   return 'manager-msg'
    return 'other'
  }

  const openTickets     = tickets.filter(t => t.status !== 'resolved')
  const resolvedTickets = tickets.filter(t => t.status === 'resolved')

  if (!mounted) return null

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        :root,[data-theme=light]{--bg:#F2F2F2;--bg-elev:#FFFFFF;--bg-sun:#EBEBEB;--fg:#141414;--fg-dim:#3a3a3a;--fg-mute:#6b6b6b;--fg-faint:#a8a8a8;--brd:#CBCBCB;--brd-s:#b5b5b5;--grn:#174D38;--grn-lt:#1f6a4d;--grn-w:#e8f2ed;--red:#4D1717;--red-w:#f5eaea;--ok:#1a7a4a;--ok-w:#e6f4ed;--warn:#8a5a00;--warn-w:#fdf4e3;--crit:#4D1717;--crit-w:#f5eaea;--shadow:0 1px 3px rgba(0,0,0,.07);--shadow-md:0 4px 14px rgba(0,0,0,.09);--shadow-pop:0 12px 36px rgba(0,0,0,.14)}
        [data-theme=dark]{--bg:#0e1410;--bg-elev:#141d18;--bg-sun:#111910;--fg:#e8ede9;--fg-dim:#b0bab3;--fg-mute:#7a897e;--fg-faint:#4a5a50;--brd:#233028;--brd-s:#2e3d34;--grn:#2a8a5e;--grn-lt:#33a872;--grn-w:#0f2318;--red:#9b3535;--red-w:#1f0e0e;--ok:#2a8a5e;--ok-w:#0f2318;--warn:#c8880a;--warn-w:#1f1600;--crit:#9b3535;--crit-w:#1f0e0e;--shadow:0 1px 3px rgba(0,0,0,.35);--shadow-md:0 4px 14px rgba(0,0,0,.45);--shadow-pop:0 12px 36px rgba(0,0,0,.55)}
        *{box-sizing:border-box;margin:0;padding:0}
        html,body,#__next{height:100vh;overflow:hidden}
        body{font-family:"Inter",-apple-system,sans-serif;font-size:13px;line-height:1.45;color:var(--fg);background:var(--bg);-webkit-font-smoothing:antialiased;transition:background .2s,color .2s}
        .shell{display:grid;grid-template-columns:220px 1fr;height:100vh;overflow:hidden}
        .sidebar{background:var(--grn);display:flex;flex-direction:column;overflow:hidden}
        .sb-head{height:48px;padding:0 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid rgba(255,255,255,.1);flex-shrink:0}
        .logomark{width:24px;height:24px;border-radius:5px;background:rgba(255,255,255,.18);color:#fff;display:grid;place-items:center;font-family:"JetBrains Mono",monospace;font-weight:700;font-size:12px;flex-shrink:0}
        .nav-lbl{padding:10px 16px 3px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.35);font-weight:600;font-family:"JetBrains Mono",monospace}
        .nav-item{display:flex;align-items:center;gap:10px;padding:6px 16px;height:32px;font-size:13px;color:rgba(255,255,255,.65);cursor:pointer;border-left:2px solid transparent;user-select:none;transition:all .12s}
        .nav-item:hover{background:rgba(255,255,255,.08);color:#fff}
        .nav-item.active{background:rgba(255,255,255,.16);color:#fff;border-left-color:#fff;font-weight:500}
        .nav-badge{margin-left:auto;font-family:"JetBrains Mono",monospace;font-size:10px;color:rgba(255,255,255,.45);background:rgba(255,255,255,.1);padding:1px 7px;border-radius:10px}
        .nav-item.active .nav-badge{color:rgba(255,255,255,.85)}
        .sb-team{padding:10px 16px;border-top:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.1)}
        .sb-foot{margin-top:auto;border-top:1px solid rgba(255,255,255,.1);padding:12px 16px;display:flex;align-items:center;gap:10px}
        .av{width:28px;height:28px;border-radius:5px;display:grid;place-items:center;font-size:11px;font-weight:700;flex-shrink:0;color:#fff;background:rgba(255,255,255,.2)}
        .u-name{font-size:12px;font-weight:500;color:#fff;line-height:1.2}
        .u-role{font-size:10px;color:rgba(255,255,255,.45);font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em}
        .theme-btn{width:28px;height:28px;border-radius:4px;display:grid;place-items:center;cursor:pointer;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.15);color:#fff;margin-left:auto;transition:background .15s}
        .theme-btn:hover{background:rgba(255,255,255,.22)}
        .main{display:grid;grid-template-rows:48px 1fr;overflow:hidden}
        .topbar{height:48px;background:var(--bg-elev);border-bottom:1px solid var(--brd);display:flex;align-items:center;padding:0 16px;gap:12px;flex-shrink:0;box-shadow:var(--shadow)}
        .crumbs{font-size:12px;color:var(--fg-mute);display:flex;align-items:center;gap:6px}
        .content{overflow:hidden;background:var(--bg)}
        .split{display:grid;grid-template-columns:1fr 440px;height:100%;overflow:hidden}
        .split-l{display:flex;flex-direction:column;overflow:hidden}
        .split-r{border-left:1px solid var(--brd);background:var(--bg-elev);display:flex;flex-direction:column;overflow:hidden}
        .fbar{display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid var(--brd);background:var(--bg-elev);height:42px;flex-shrink:0}
        .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid var(--brd);background:var(--bg-elev);color:var(--fg);font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
        .btn:hover{background:var(--bg-sun)}
        .btn-p{background:var(--grn)!important;color:#fff!important;border-color:var(--grn)!important}
        .btn-p:hover{background:var(--grn-lt)!important}
        .btn-r{background:var(--red)!important;color:#fff!important;border-color:var(--red)!important}
        .btn-sm{height:24px;padding:0 8px;font-size:11px}
        .btn-g{background:transparent!important;border-color:transparent!important;color:var(--fg-mute)!important}
        .btn-g:hover{background:var(--bg-sun)!important;color:var(--fg)!important}
        .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:var(--bg-sun);color:var(--fg-dim);border:1px solid var(--brd);white-space:nowrap}
        .pill-ok{background:var(--ok-w);color:var(--ok);border-color:transparent}
        .pill-warn{background:var(--warn-w);color:var(--warn);border-color:transparent}
        .pill-crit{background:var(--crit-w);color:var(--crit);border-color:transparent}
        .pill-grn{background:var(--grn-w);color:var(--grn);border-color:transparent}
        .pill-pur{background:#f0edf8;color:#5b3d8a;border-color:transparent}
        [data-theme=dark] .pill-pur{background:#1e1525;color:#b39ddb}
        .card{background:var(--bg-elev);border:1px solid var(--brd);border-radius:6px;box-shadow:var(--shadow)}
        .c-head{padding:10px 14px;border-bottom:1px solid var(--brd);display:flex;align-items:center;gap:10px;min-height:40px}
        .c-head h3{margin:0;font-size:12px;font-weight:600}
        table.dt{width:100%;border-collapse:collapse;font-size:12px}
        table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--fg-mute);padding:8px 12px;background:var(--bg-sun);border-bottom:1px solid var(--brd);font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
        table.dt td{padding:8px 12px;border-bottom:1px solid var(--brd);vertical-align:middle}
        table.dt tr{cursor:pointer;transition:background .1s}
        table.dt tr:hover td{background:var(--bg-sun)}
        table.dt tr.sel td{background:var(--grn-w)}
        .bar{height:5px;background:var(--bg-sun);border-radius:3px;overflow:hidden;border:1px solid var(--brd)}
        .bar-f{height:100%;transition:width .4s}
        .kb-c{background:var(--bg-sun);border:1px solid var(--brd);border-radius:4px;padding:8px 10px;font-size:12px;color:var(--fg-dim);line-height:1.6}
        .status-toggle{display:flex;gap:2px;padding:3px;background:var(--bg-sun);border-radius:4px;border:1px solid var(--brd)}
        .st-opt{padding:4px 10px;border-radius:3px;font-size:10px;font-weight:500;cursor:pointer;color:var(--fg-mute);transition:all .12s;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em}
        .st-opt:hover{color:var(--fg)}
        .st-opt.on-avail{background:var(--ok-w);color:var(--ok)}
        .st-opt.on-busy{background:var(--warn-w);color:var(--warn)}
        .st-opt.on-away{background:var(--crit-w);color:var(--crit)}
        .mono{font-family:"JetBrains Mono",monospace}
        .muted{color:var(--fg-mute)}
        .small{font-size:11px}
        .tiny{font-size:10px}
        .grow{flex:1}
        .row{display:flex;align-items:center;gap:8px}
        .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .fade{animation:fade .25s ease-out both}
        @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
        .toast-tray{position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;gap:8px;z-index:200;pointer-events:none}
        .toast{background:var(--bg-elev);border:1px solid var(--brd);border-radius:6px;padding:12px 16px;box-shadow:var(--shadow-pop);font-size:12px;pointer-events:auto;animation:tin .3s ease-out;display:flex;align-items:flex-start;gap:10px;min-width:300px}
        @keyframes tin{from{transform:translateX(20px);opacity:0}to{transform:translateX(0);opacity:1}}
        ::-webkit-scrollbar{width:6px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:var(--brd);border-radius:3px}
        input,textarea,select{font-family:inherit;font-size:12px;background:var(--bg-sun);border:1px solid var(--brd);color:var(--fg);border-radius:4px;padding:6px 10px;width:100%;outline:none;transition:border-color .15s}
        input:focus,textarea:focus{border-color:var(--grn)}
        textarea{resize:vertical;line-height:1.5}
        hr.div{border:none;border-top:1px solid var(--brd);margin:8px 0}
        .sec-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--fg-mute);font-family:"JetBrains Mono",monospace;margin-bottom:6px}
        .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--fg-faint);flex-shrink:0}
        .dot-ok{background:var(--ok)}.dot-warn{background:var(--warn)}.dot-crit{background:var(--crit)}.dot-grn{background:var(--grn)}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
        .pulse{animation:pulse 1.8s ease-in-out infinite}
        .chat-shell{display:flex;flex-direction:column;height:100%;overflow:hidden}
        .chat-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:var(--bg-sun)}
        .cmsg{display:flex;flex-direction:column;max-width:75%}
        .cmsg.mine{align-self:flex-end;align-items:flex-end}
        .cmsg.other{align-self:flex-start;align-items:flex-start}
        .cmsg.system{align-self:center;align-items:center}
        .cbubble{padding:8px 12px;border-radius:8px;font-size:12px;line-height:1.5;word-break:break-word}
        .cbubble.mine{background:var(--grn);color:#fff;border-radius:8px 8px 2px 8px}
        .cbubble.other{background:var(--bg-elev);border:1px solid var(--brd);border-radius:8px 8px 8px 2px}
        .cbubble.manager-msg{background:#f0edf8;border:1px solid rgba(91,61,138,.15);border-radius:8px 8px 8px 2px}
        [data-theme=dark] .cbubble.manager-msg{background:#1e1525;border-color:rgba(179,157,219,.15)}
        .cbubble.system{background:transparent;color:var(--fg-mute);font-size:11px;font-style:italic;padding:2px 8px;border:none}
        .cmeta{font-size:10px;color:var(--fg-mute);font-family:"JetBrains Mono",monospace;margin-bottom:3px}
        .cts{font-size:10px;color:var(--fg-faint);font-family:"JetBrains Mono",monospace;margin-top:3px}
        .chat-input-row{padding:10px 14px;border-top:1px solid var(--brd);display:flex;gap:8px;align-items:center;background:var(--bg-elev);flex-shrink:0}
        .chat-inp{flex:1;padding:8px 14px;background:var(--bg-sun);border:1px solid var(--brd);color:var(--fg);font-family:inherit;font-size:13px;outline:none;border-radius:20px;transition:border-color .15s;width:auto}
        .chat-inp:focus{border-color:var(--grn);background:var(--bg-elev)}
        .chat-inp::placeholder{color:var(--fg-faint)}
        .chat-send{width:34px;height:34px;border-radius:50%;background:var(--grn);border:none;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s}
        .chat-send:hover{background:var(--grn-lt)}
        .chat-send:disabled{background:var(--brd);cursor:not-allowed}
        .online-dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 4px var(--ok);display:inline-block}
      `}</style>

      <div className="shell">
        {/* ── SIDEBAR ── */}
        <div className="sidebar">
          <div className="sb-head">
            <div className="logomark">N</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: '#fff', letterSpacing: '-.01em' }}>NexusDesk</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,.45)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em' }}>Engineer</div>
            </div>
            <div className="theme-btn" onClick={toggleTheme} title="Toggle theme">
              {theme === 'light'
                ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
                : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>}
            </div>
          </div>

          {/* Team info block in sidebar */}
          {teamInfo && (
            <div className="sb-team">
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,.35)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 4 }}>My Team</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#fff', marginBottom: 2 }}>{teamInfo.name}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,.45)', fontFamily: '"JetBrains Mono",monospace' }}>{teamInfo.team_id}</span>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,.35)' }}>·</span>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,.5)' }}>{teamInfo.role_in_team}</span>
              </div>
              {teamInfo.manager_name && (
                <div style={{ fontSize: 10, color: 'rgba(255,255,255,.4)', marginTop: 3 }}>
                  Mgr: <span style={{ color: 'rgba(255,255,255,.65)' }}>{teamInfo.manager_name}</span>
                </div>
              )}
            </div>
          )}

          <div style={{ marginTop: 8 }}>
            <div className="nav-lbl">Work</div>
            {([
              { id: 'queue',   label: 'Ticket Queue',   icon: 'inbox' },
              { id: 'kb',      label: 'Knowledge Base', icon: 'book'  },
              { id: 'history', label: 'History',        icon: 'clock' },
            ] as const).map(n => (
              <div key={n.id} className={`nav-item ${tab === n.id ? 'active' : ''}`} onClick={() => setTab(n.id)}>
                {n.id === 'queue' && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>}
                {n.id === 'kb'    && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>}
                {n.id === 'history' && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>}
                {n.label}
                {n.id === 'queue' && <span className="nav-badge">{openTickets.length}</span>}
              </div>
            ))}

            {/* Team Chat nav item — only if in a team */}
            {teamInfo && (
              <>
                <div className="nav-lbl" style={{ marginTop: 8 }}>Team</div>
                <div className={`nav-item ${tab === 'chat' ? 'active' : ''}`} onClick={() => setTab('chat')}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                  Team Chat
                  {chatConnected && tab === 'chat' && (
                    <span className="nav-badge" style={{ background: 'rgba(26,122,74,.3)', color: 'rgba(255,255,255,.8)' }}>
                      {onlineCount} online
                    </span>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="sb-foot">
            <div className="av">{engName?.charAt(0)?.toUpperCase() || 'E'}</div>
            <div>
              <div className="u-name">{engName || 'Engineer'}</div>
              <div className="u-role">{engId}</div>
            </div>
          </div>
        </div>

        {/* ── MAIN ── */}
        <div className="main">
          {/* Topbar */}
          <div className="topbar">
            <div className="crumbs">
              <span>NexusDesk</span>
              <span style={{ color: 'var(--fg-faint)' }}>/</span>
              <b>{{ queue: 'Ticket Queue', kb: 'Knowledge Base', history: 'History', chat: `${teamInfo?.name || 'Team'} Chat` }[tab]}</b>
            </div>
            <span className="grow" />
            {tab !== 'chat' && (
              <div className="status-toggle" style={{ marginLeft: 12 }}>
                {[
                  { s: 'available', l: 'Avail', c: 'on-avail' },
                  { s: 'busy',      l: 'Busy',  c: 'on-busy'  },
                  { s: 'away',      l: 'Away',  c: 'on-away'  },
                ].map(o => (
                  <div key={o.s} className={`st-opt ${availability === o.s ? o.c : ''}`} onClick={() => setAvail(o.s)}>
                    {availability === o.s && <span className={`dot dot-${o.s === 'available' ? 'ok' : o.s === 'busy' ? 'warn' : 'crit'} pulse`} style={{ marginRight: 4 }} />}
                    {o.l}
                  </div>
                ))}
              </div>
            )}
            {tab === 'chat' && chatConnected && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="online-dot"/>
                <span style={{ fontSize: 12, color: 'var(--ok)' }}>{onlineCount} online</span>
              </div>
            )}
            <button className="btn btn-g btn-sm" onClick={() => { localStorage.clear(); window.location.replace('/auth/login') }}>Sign out</button>
          </div>

          {/* ── CONTENT ── */}
          <div className="content" style={{ height: 'calc(100vh - 48px)', overflowY: 'hidden' }}>

            {/* ── QUEUE TAB ── */}
            {tab === 'queue' && (
              <div className="split" style={{ height: '100%' }}>
                <div className="split-l">
                  {stats && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 1, background: 'var(--brd)', borderBottom: '1px solid var(--brd)', flexShrink: 0 }}>
                      {[
                        { l: 'Active',    v: stats.active_tickets,         c: 'var(--warn)' },
                        { l: 'This Week', v: stats.this_week_resolved,      c: 'var(--ok)'   },
                        { l: 'Total',     v: stats.total_resolved,           c: 'var(--grn)'  },
                        { l: 'SLA',       v: `${stats.sla_compliance_rate}%`, c: 'var(--ok)'  },
                        { l: 'Avg',       v: `${stats.avg_resolution_time}m`, c: '#2a6bab'    },
                      ].map((s, i) => (
                        <div key={i} style={{ background: 'var(--bg-elev)', padding: '10px 14px' }}>
                          <div style={{ fontSize: 10, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 3 }}>{s.l}</div>
                          <div style={{ fontSize: 20, fontWeight: 700, color: s.c, fontFamily: '"JetBrains Mono",monospace', letterSpacing: '-.02em' }}>{loading ? '—' : s.v}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="fbar">
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace', textTransform: 'uppercase', letterSpacing: '.06em' }}>Queue</span>
                    <span className="pill">{openTickets.length} open</span>
                    <span className="grow" />
                    <button className="btn btn-sm" onClick={fetchData}>↻ Refresh</button>
                  </div>

                  <div style={{ flex: 1, overflowY: 'auto' }}>
                    <table className="dt">
                      <thead>
                        <tr><th>ID</th><th>Issue</th><th>User</th><th>Domain</th><th>Priority</th><th>Status</th><th>Created</th></tr>
                      </thead>
                      <tbody>
                        {loading ? (
                          <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: 'var(--fg-mute)' }}>Loading tickets...</td></tr>
                        ) : openTickets.length === 0 ? (
                          <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: 'var(--fg-mute)' }}>All caught up — no open tickets</td></tr>
                        ) : openTickets.map(t => (
                          <tr key={t.id} className={selected?.id === t.id ? 'sel' : ''} onClick={() => { setSelected(selected?.id === t.id ? null : t); setNotes('') }}>
                            <td><span className="mono" style={{ fontSize: 11, fontWeight: 600, color: 'var(--grn)' }}>{t.ticket_number}</span></td>
                            <td style={{ maxWidth: 220 }}>
                              <div className="trunc" style={{ fontWeight: 500 }}>{t.title}</div>
                              {t.cnn_image_result && <span className="pill pill-pur" style={{ marginTop: 3 }}>📸 Screenshot</span>}
                            </td>
                            <td>
                              <div style={{ fontSize: 12 }}>{t.user_name}</div>
                              {t.user_city && <div className="tiny muted">{t.user_city}</div>}
                            </td>
                            <td><span className="pill">{dLabel(t.domain)}</span></td>
                            <td><span className={`pill ${pPill(t.priority)}`}>{t.priority}</span></td>
                            <td><span className={`pill ${sPill(t.status)}`}>{t.status.replace('_', ' ')}</span></td>
                            <td className="small muted mono">{fmtTime(t.created_at, t.user_timezone)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {resolvedTickets.length > 0 && (
                      <div style={{ padding: '12px 14px', borderTop: '1px solid var(--brd)' }}>
                        <div className="sec-lbl" style={{ marginBottom: 8 }}>Recently Resolved · {resolvedTickets.length}</div>
                        <table className="dt">
                          <tbody>
                            {resolvedTickets.slice(0, 5).map(t => (
                              <tr key={t.id} onClick={() => { setSelected(selected?.id === t.id ? null : t); setNotes('') }} style={{ opacity: 0.7 }}>
                                <td><span className="mono" style={{ fontSize: 11, color: 'var(--grn)' }}>{t.ticket_number}</span></td>
                                <td>{t.title}</td>
                                <td><span className="pill pill-ok">Resolved</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right panel */}
                <div className="split-r fade">
                  {!selected ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--fg-mute)', gap: 10 }}>
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>Select a ticket</div>
                      <div className="small muted">Click any row to view details</div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
                      <div style={{ background: 'var(--grn)', padding: '12px 16px', flexShrink: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div>
                            <div style={{ fontSize: 10, color: 'rgba(255,255,255,.5)', fontFamily: '"JetBrains Mono",monospace', marginBottom: 4 }}>{selected.ticket_number}</div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: '#fff', lineHeight: 1.3, maxWidth: 340 }}>{selected.title}</div>
                          </div>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0, marginLeft: 10 }}>
                            <span className={`pill ${pPill(selected.priority)}`}>{selected.priority}</span>
                            <button className="btn btn-sm btn-g" style={{ color: 'rgba(255,255,255,.7)' }} onClick={() => setSelected(null)}>✕</button>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                          <span className={`pill ${sPill(selected.status)}`}>{selected.status.replace('_', ' ')}</span>
                          <span className="pill">{dLabel(selected.domain)}</span>
                          {selected.sla_breached && <span className="pill pill-crit">SLA Breach</span>}
                        </div>
                      </div>

                      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <div className="card">
                          <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>User</span></div>
                          <div style={{ padding: '10px 14px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <div className="av" style={{ width: 32, height: 32, background: 'var(--grn-w)', color: 'var(--grn)', fontSize: 13, fontWeight: 700 }}>{selected.user_name?.charAt(0)?.toUpperCase()}</div>
                              <div>
                                <div style={{ fontWeight: 600, fontSize: 13 }}>{selected.user_name}</div>
                                <div className="small muted">{selected.user_email}</div>
                                {selected.user_city && <div className="small muted">📍 {selected.user_city}, {selected.user_country}</div>}
                              </div>
                            </div>
                            <hr className="div" />
                            <div className="small muted">Created {fmtTime(selected.created_at, selected.user_timezone)}</div>
                          </div>
                        </div>

                        <div className="card">
                          <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>Issue Description</span></div>
                          <div className="kb-c" style={{ margin: 10, borderRadius: 4 }}>{selected.description}</div>
                          {selected.steps_tried && (
                            <>
                              <div className="c-head" style={{ borderTop: '1px solid var(--brd)' }}><span className="sec-lbl" style={{ margin: 0 }}>Steps Tried</span></div>
                              <div className="kb-c" style={{ margin: 10, borderRadius: 4 }}>{selected.steps_tried}</div>
                            </>
                          )}
                        </div>

                        {selected.ai_diagnosis && (
                          <div className="card">
                            <div className="c-head">
                              <span className="dot dot-grn" />
                              <span className="sec-lbl" style={{ margin: 0 }}>AI Diagnosis</span>
                            </div>
                            <div style={{ padding: '10px 14px', fontSize: 12, lineHeight: 1.7, color: 'var(--fg-dim)' }}>{selected.ai_diagnosis}</div>
                          </div>
                        )}

                        {selected.cnn_image_result && (
                          <div className="card">
                            <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>Screenshot · CNN Detection</span></div>
                            <div style={{ padding: 10 }}>
                              <div className="kb-c" style={{ marginBottom: 8 }}>
                                {selected.cnn_image_result.includes(' |') ? selected.cnn_image_result.split(' | ').slice(1).join(' · ') : 'Screenshot uploaded by user'}
                              </div>
                              {getScreenshotUrl(selected.cnn_image_result) && (
                                <ScreenshotImage url={getScreenshotUrl(selected.cnn_image_result)!} />
                              )}
                            </div>
                          </div>
                        )}

                        <div className="card">
                          <div className="c-head">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--grn)" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>
                            <span className="sec-lbl" style={{ margin: 0 }}>Knowledge Base Similarity</span>
                          </div>
                          <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {kbLoading ? (
                              <div className="kb-c" style={{ textAlign: 'center' }}>Searching knowledge base...</div>
                            ) : kbResults.length === 0 ? (
                              <div className="kb-c muted" style={{ textAlign: 'center' }}>No relevant KB articles found</div>
                            ) : kbResults.map((r, i) => (
                              <div key={i} style={{ background: 'var(--bg-sun)', border: '1px solid var(--brd)', borderLeft: `3px solid ${simColor(r.cosine_similarity)}`, borderRadius: 4, padding: '8px 10px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                  <span style={{ fontSize: 12, fontWeight: 600, flex: 1, marginRight: 8 }}>{r.title}</span>
                                  <span className="pill" style={{ background: `${simColor(r.cosine_similarity)}18`, color: simColor(r.cosine_similarity), border: 'none', fontFamily: '"JetBrains Mono",monospace' }}>
                                    {r.cosine_similarity}% {simLabel(r.cosine_similarity)}
                                  </span>
                                </div>
                                <div className="small muted mono" style={{ marginBottom: 4 }}>{r.filename}</div>
                                <div style={{ fontSize: 11, color: 'var(--fg-dim)', lineHeight: 1.6, display: kbExpanded === i ? 'block' : '-webkit-box', WebkitLineClamp: kbExpanded === i ? undefined : 2, WebkitBoxOrient: 'vertical' as any, overflow: kbExpanded === i ? 'visible' : 'hidden' }}>
                                  {r.content}
                                </div>
                                <button onClick={() => setKbExpanded(kbExpanded === i ? null : i)} style={{ fontSize: 10, color: 'var(--grn)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', marginTop: 4, padding: 0 }}>
                                  {kbExpanded === i ? 'Show less ↑' : 'Read more ↓'}
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>

                        {selected.status !== 'resolved' ? (
                          <div className="card">
                            <div className="c-head"><span className="sec-lbl" style={{ margin: 0 }}>Resolution Notes</span></div>
                            <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                              <textarea rows={4} placeholder="Document what you did to resolve this issue..." value={notes} onChange={e => setNotes(e.target.value)} />
                              <div style={{ display: 'flex', gap: 8 }}>
                                {selected.status === 'open' && (
                                  <button className="btn" style={{ flex: 1 }} onClick={markInProgress}>Mark In Progress</button>
                                )}
                                <button className="btn btn-p" style={{ flex: 2 }} disabled={updating || !notes.trim()} onClick={resolveTicket}>
                                  {updating ? 'Saving...' : 'Mark Resolved ✓'}
                                </button>
                              </div>
                            </div>
                          </div>
                        ) : selected.resolution_notes ? (
                          <div className="card">
                            <div className="c-head"><span className="dot dot-ok" /><span className="sec-lbl" style={{ margin: 0 }}>Resolution Notes</span></div>
                            <div style={{ padding: '10px 14px', fontSize: 12, lineHeight: 1.7, color: 'var(--fg-dim)' }}>{selected.resolution_notes}</div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── KB TAB ── */}
            {tab === 'kb' && (
              <div style={{ height: '100%', overflowY: 'auto', padding: 16 }}>
                <div style={{ maxWidth: 760, margin: '0 auto' }}>
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Knowledge Base</div>
                    <div className="small muted">Semantic search across all IT documentation and resolved tickets</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                    <input placeholder="Search docs..." value={kbSearch} onChange={e => setKbSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchKB()} style={{ flex: 1 }} />
                    <button className="btn btn-p" onClick={searchKB} disabled={kbSearching || !kbSearch.trim()}>
                      {kbSearching ? 'Searching...' : 'Search'}
                    </button>
                  </div>
                  {kbSearchRes.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div className="small muted">{kbSearchRes.length} results for "{kbSearch}"</div>
                      {kbSearchRes.map((r, i) => (
                        <div key={i} className="card" style={{ borderLeft: `3px solid ${simColor(r.cosine_similarity)}` }}>
                          <div className="c-head">
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>{r.title}</div>
                              <div className="small muted mono">{r.filename}</div>
                            </div>
                            <span className="pill" style={{ background: `${simColor(r.cosine_similarity)}18`, color: simColor(r.cosine_similarity), border: 'none' }}>
                              {r.cosine_similarity}% {simLabel(r.cosine_similarity)}
                            </span>
                          </div>
                          <div style={{ padding: '10px 14px', fontSize: 12, color: 'var(--fg-dim)', lineHeight: 1.7 }}>{r.content}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {kbSearchRes.length === 0 && !kbSearching && (
                    <div className="card" style={{ padding: '48px 24px', textAlign: 'center' }}>
                      <div style={{ fontSize: 28, marginBottom: 8 }}>📖</div>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>Search the knowledge base</div>
                      <div className="small muted">Type a query above and press Enter</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── HISTORY TAB ── */}
            {tab === 'history' && (
              <div style={{ height: '100%', overflowY: 'auto', padding: 16 }}>
                <div style={{ maxWidth: 900, margin: '0 auto' }}>
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Resolved Tickets</div>
                    <div className="small muted">Your full resolution history · {resolvedTickets.length} tickets</div>
                  </div>
                  {stats && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, marginBottom: 16 }}>
                      {[
                        { l: 'Total Resolved', v: stats.total_resolved },
                        { l: 'Avg Resolution', v: `${stats.avg_resolution_time}m` },
                        { l: 'SLA Compliance', v: `${stats.sla_compliance_rate}%` },
                      ].map((s, i) => (
                        <div key={i} className="card" style={{ padding: '12px 14px' }}>
                          <div className="tiny muted">{s.l}</div>
                          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4, fontFamily: '"JetBrains Mono",monospace', letterSpacing: '-.02em' }}>{s.v}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="card">
                    <table className="dt">
                      <thead><tr><th>ID</th><th>Issue</th><th>User</th><th>Domain</th><th>Created</th></tr></thead>
                      <tbody>
                        {resolvedTickets.length === 0 ? (
                          <tr><td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--fg-mute)' }}>No resolved tickets yet</td></tr>
                        ) : resolvedTickets.map(t => (
                          <tr key={t.id} onClick={() => { setSelected(t); setTab('queue') }}>
                            <td><span className="mono" style={{ fontSize: 11, color: 'var(--grn)', fontWeight: 600 }}>{t.ticket_number}</span></td>
                            <td style={{ maxWidth: 260 }}><div className="trunc">{t.title}</div></td>
                            <td className="small muted">{t.user_name}</td>
                            <td><span className="pill">{dLabel(t.domain)}</span></td>
                            <td className="small muted mono">{fmtTime(t.created_at, t.user_timezone)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* ── CHAT TAB ── */}
            {tab === 'chat' && (
              <div className="chat-shell">

                {/* Team info header */}
                {teamInfo && (
                  <div style={{ padding: '10px 16px', background: 'var(--bg-elev)', borderBottom: '1px solid var(--brd)', display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 6, background: 'var(--grn)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                      {teamInfo.name.charAt(0)}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{teamInfo.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--fg-mute)', fontFamily: '"JetBrains Mono",monospace' }}>
                        {teamInfo.team_id} · {teamInfo.domain_focus?.slice(0, 2).map(d => dLabel(d)).join(', ')} · {teamInfo.member_count} members
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 12, color: 'var(--fg-mute)' }}>Manager: <span style={{ fontWeight: 500, color: 'var(--fg)' }}>{teamInfo.manager_name}</span></div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end', marginTop: 2 }}>
                        <span className="online-dot" style={{ width: 6, height: 6, background: chatConnected ? 'var(--ok)' : 'var(--brd)', boxShadow: chatConnected ? '0 0 4px var(--ok)' : 'none' }}/>
                        <span style={{ fontSize: 11, color: chatConnected ? 'var(--ok)' : 'var(--fg-mute)' }}>
                          {chatConnected ? `${onlineCount} online` : 'Connecting...'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Messages */}
                <div className="chat-msgs">
                  {chatMessages.length === 0 && (
                    <div style={{ textAlign: 'center', color: 'var(--fg-mute)', fontSize: 12, marginTop: 60 }}>
                      No messages yet. Say hello to your team!
                    </div>
                  )}
                  {chatMessages.map((msg, i) => {
                    const isMe     = msg.sender_id === currentUserId
                    const isSystem = msg.type === 'system'
                    return (
                      <div key={msg.id || i} className={`cmsg ${isSystem ? 'system' : isMe ? 'mine' : 'other'}`}>
                        {!isSystem && !isMe && (
                          <div className="cmeta" style={{ color: roleColor(msg.sender_role) }}>
                            {msg.sender_name} · {msg.sender_role}
                          </div>
                        )}
                        <div className={`cbubble ${getBubbleClass(msg)}`}>{msg.message}</div>
                        {!isSystem && <div className="cts">{chatTime(msg.timestamp)}</div>}
                      </div>
                    )
                  })}
                  <div ref={chatBottom}/>
                </div>

                {/* Input */}
                <div className="chat-input-row">
                  <input
                    className="chat-inp"
                    placeholder={chatConnected ? `Message ${teamInfo?.name || 'your team'}...` : 'Connecting...'}
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={handleChatKey}
                    disabled={!chatConnected}
                  />
                  <button className="chat-send" onClick={sendChatMessage} disabled={!chatConnected || !chatInput.trim()}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="22" y1="2" x2="11" y2="13"/>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="toast-tray">
          <div className="toast">
            <div style={{ width: 22, height: 22, borderRadius: 4, background: toast.type === 'ok' ? 'var(--ok-w)' : 'var(--crit-w)', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
              {toast.type === 'ok'
                ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--ok)" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--crit)" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>}
            </div>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 2 }}>{toast.title}</div>
              <div className="small muted">{toast.desc}</div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}