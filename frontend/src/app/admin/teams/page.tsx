// Location: ./frontend/src/app/admin/teams/page.tsx
'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL
const WS_URL = process.env.NEXT_PUBLIC_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'

interface Manager {
  id: string
  full_name: string
  email: string
  is_active: boolean
  city: string
  country: string
  timezone: string
  teams: string[]
}

interface TeamMember {
  id: string
  user_id: string
  full_name: string
  email: string
  engineer_id: string
  role_in_team: string
  domain_expertise: string[]
  availability_status: string
  active_ticket_count: number
  joined_at: string
}

interface Team {
  id: string
  team_id: string
  name: string
  description: string
  domain_focus: string[]
  region: string
  timezone: string
  manager_id: string
  manager_name: string
  manager_email: string
  is_active: boolean
  max_ticket_capacity: number
  active_ticket_count: number
  total_resolved: number
  avg_resolution_time: number
  sla_compliance_rate: number
  member_count: number
  members: TeamMember[]
  created_at: string
}

interface ChatMessage {
  id: string
  message: string
  sender_id: string
  sender_name: string
  sender_role: string
  timestamp: string
  type?: 'message' | 'system'
  online_count?: number
}

const DOMAINS = [
  { v: 'networking', l: 'Networking' }, { v: 'hardware', l: 'Hardware' },
  { v: 'software', l: 'Software' }, { v: 'security', l: 'Security' },
  { v: 'email_communication', l: 'Email & Comm' }, { v: 'identity_access', l: 'Identity & Access' },
  { v: 'database', l: 'Database' }, { v: 'cloud', l: 'Cloud' },
  { v: 'infrastructure', l: 'Infrastructure' }, { v: 'devops', l: 'DevOps' },
  { v: 'erp_business_apps', l: 'ERP & Business' }, { v: 'endpoint_management', l: 'Endpoint Mgmt' },
]

const REGIONS = ['India', 'Europe', 'US', 'Asia Pacific', 'Middle East', 'Africa']

const TIMEZONES = [
  'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin',
  'America/New_York', 'America/Chicago', 'America/Los_Angeles',
  'Africa/Nairobi', 'Africa/Lagos', 'UTC',
]

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .tm * { box-sizing: border-box; }
  .tm { font-family: "Inter", -apple-system, sans-serif; font-size: 13px; color: #141414; background: #F2F2F2; min-height: 100%; }
  .tm .card { background: #fff; border: 1px solid #CBCBCB; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.07); }
  .tm .c-head { padding: 10px 14px; border-bottom: 1px solid #CBCBCB; display: flex; align-items: center; gap: 10px; min-height: 40px; }
  .tm .c-head h3 { margin: 0; font-size: 12px; font-weight: 600; letter-spacing: -.01em; }
  .tm .pill { display: inline-flex; align-items: center; gap: 4px; height: 20px; padding: 0 7px; border-radius: 10px; font-size: 10px; font-weight: 600; font-family: "JetBrains Mono", monospace; text-transform: uppercase; letter-spacing: .04em; background: #EBEBEB; color: #3a3a3a; border: 1px solid #CBCBCB; white-space: nowrap; }
  .tm .pill-ok { background: #e6f4ed; color: #1a7a4a; border-color: transparent; }
  .tm .pill-warn { background: #fdf4e3; color: #8a5a00; border-color: transparent; }
  .tm .pill-crit { background: #f5eaea; color: #4D1717; border-color: transparent; }
  .tm .pill-grn { background: #e8f2ed; color: #174D38; border-color: transparent; }
  .tm .pill-pur { background: #f0edf8; color: #5b3d8a; border-color: transparent; }
  .tm .pill-blue { background: #e8f0fd; color: #1a56b0; border-color: transparent; }
  .tm .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #a0a0a0; flex-shrink: 0; }
  .tm .dot-ok { background: #1a7a4a; }
  .tm .dot-warn { background: #8a5a00; }
  .tm .dot-crit { background: #4D1717; }
  .tm table.dt { width: 100%; border-collapse: collapse; font-size: 12px; }
  .tm table.dt th { text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: #6b6b6b; padding: 8px 12px; background: #EBEBEB; border-bottom: 1px solid #CBCBCB; font-weight: 600; font-family: "JetBrains Mono", monospace; white-space: nowrap; }
  .tm table.dt td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
  .tm table.dt tr { cursor: pointer; }
  .tm table.dt tr:hover td { background: #f9f9f9; }
  .tm table.dt tr.sel td { background: #e8f2ed; }
  .tm .btn { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 4px; border: 1px solid #CBCBCB; background: #fff; color: #141414; font-family: inherit; font-size: 12px; font-weight: 500; cursor: pointer; white-space: nowrap; transition: background .1s; }
  .tm .btn:hover { background: #EBEBEB; }
  .tm .btn-p { background: #174D38 !important; color: #fff !important; border-color: #174D38 !important; }
  .tm .btn-p:hover { background: #1f6a4d !important; }
  .tm .btn-r { background: #4D1717 !important; color: #fff !important; border-color: #4D1717 !important; }
  .tm .btn-r:hover { background: #6b2020 !important; }
  .tm .btn-sm { height: 24px; padding: 0 8px; font-size: 11px; }
  .tm .btn-g { background: transparent !important; border-color: transparent !important; color: #6b6b6b !important; }
  .tm .chip { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 11px; background: #EBEBEB; border: 1px solid #CBCBCB; font-size: 11px; color: #3a3a3a; cursor: pointer; font-weight: 500; transition: all .1s; }
  .tm .chip:hover, .tm .chip.on { background: #174D38; color: #fff; border-color: #174D38; }
  .tm .bar { height: 5px; background: #EBEBEB; border-radius: 3px; overflow: hidden; border: 1px solid #CBCBCB; }
  .tm .bar-f { height: 100%; transition: width .4s; border-radius: 3px; }
  .tm .mono { font-family: "JetBrains Mono", monospace; }
  .tm .muted { color: #6b6b6b; }
  .tm .small { font-size: 11px; }
  .tm .tiny { font-size: 10px; }
  .tm .trunc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tm .row { display: flex; align-items: center; gap: 8px; }
  .tm .grow { flex: 1; }
  .tm .lbl { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: #6b6b6b; font-family: "JetBrains Mono", monospace; display: block; margin-bottom: 5px; }
  .tm input, .tm select, .tm textarea { width: 100%; padding: 8px 10px; border: 1px solid #CBCBCB; border-radius: 4px; font-family: inherit; font-size: 13px; color: #141414; background: #fff; outline: none; transition: border-color .15s; }
  .tm input:focus, .tm select:focus, .tm textarea:focus { border-color: #174D38; }
  .tm .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.35); z-index: 100; display: flex; align-items: center; justify-content: center; }
  .tm .modal { background: #fff; border-radius: 8px; border: 1px solid #CBCBCB; width: 560px; max-height: 88vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,.12); }
  .tm .modal-head { padding: 16px 20px; border-bottom: 1px solid #CBCBCB; display: flex; align-items: center; justify-content: space-between; }
  .tm .modal-head h2 { margin: 0; font-size: 14px; font-weight: 600; }
  .tm .modal-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .tm .modal-foot { padding: 14px 20px; border-top: 1px solid #CBCBCB; display: flex; gap: 8px; justify-content: flex-end; }
  .tm .tab { display: flex; gap: 2px; background: #EBEBEB; border-radius: 6px; padding: 3px; }
  .tm .tab-btn { flex: 1; height: 28px; border: none; background: transparent; font-family: inherit; font-size: 12px; font-weight: 500; color: #6b6b6b; cursor: pointer; border-radius: 4px; transition: all .15s; }
  .tm .tab-btn.on { background: #fff; color: #141414; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .tm .sec-lbl { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: #6b6b6b; font-family: "JetBrains Mono", monospace; }
  .tm .chat-wrap { display: flex; flex-direction: column; height: 420px; }
  .tm .chat-msgs { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; background: #fafafa; }
  .tm .chat-msg { display: flex; flex-direction: column; gap: 2px; max-width: 80%; }
  .tm .chat-msg.mine { align-self: flex-end; align-items: flex-end; }
  .tm .chat-msg.other { align-self: flex-start; align-items: flex-start; }
  .tm .chat-msg.system { align-self: center; align-items: center; }
  .tm .chat-bubble { padding: 7px 11px; border-radius: 8px; font-size: 12px; line-height: 1.5; word-break: break-word; }
  .tm .chat-bubble.mine { background: #174D38; color: #fff; border-radius: 8px 8px 2px 8px; }
  .tm .chat-bubble.other { background: #fff; border: 1px solid #CBCBCB; color: #141414; border-radius: 8px 8px 8px 2px; }
  .tm .chat-bubble.system { background: transparent; color: #6b6b6b; font-size: 11px; font-style: italic; border: none; padding: 2px 8px; }
  .tm .chat-meta { font-size: 10px; color: #6b6b6b; font-family: "JetBrains Mono", monospace; }
  .tm .chat-input-wrap { padding: 10px 14px; border-top: 1px solid #CBCBCB; display: flex; gap: 8px; background: #fff; }
  .tm .chat-input { flex: 1; padding: 8px 12px; border: 1px solid #CBCBCB; border-radius: 20px; font-family: inherit; font-size: 13px; outline: none; transition: border-color .15s; }
  .tm .chat-input:focus { border-color: #174D38; }
  .tm .chat-send { height: 34px; width: 34px; border-radius: 50%; background: #174D38; border: none; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .15s; }
  .tm .chat-send:hover { background: #1f6a4d; }
  .tm .chat-send:disabled { background: #CBCBCB; cursor: not-allowed; }
  .tm .online-dot { width: 7px; height: 7px; border-radius: 50%; background: #1a7a4a; display: inline-block; box-shadow: 0 0 4px #1a7a4a; }
  .tm .detail-tabs { display: flex; gap: 0; border-bottom: 1px solid #CBCBCB; }
  .tm .detail-tab { padding: 8px 14px; font-size: 12px; font-weight: 500; color: #6b6b6b; cursor: pointer; border-bottom: 2px solid transparent; transition: all .15s; background: none; border-top: none; border-left: none; border-right: none; font-family: inherit; }
  .tm .detail-tab.on { color: #174D38; border-bottom-color: #174D38; }
`

export default function TeamsPage() {
  const [tab, setTab] = useState<'teams' | 'managers'>('teams')
  const [detailTab, setDetailTab] = useState<'info' | 'members' | 'chat'>('info')
  const [teams, setTeams] = useState<Team[]>([])
  const [managers, setManagers] = useState<Manager[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Team | null>(null)
  const [search, setSearch] = useState('')
  const [regionFilter, setRegionFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatConnected, setChatConnected] = useState(false)
  const [onlineCount, setOnlineCount] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const chatBottomRef = useRef<HTMLDivElement>(null)
  const currentUserId = typeof window !== 'undefined' ? sessionStorage.getItem('user_id') || '' : ''

  // Modals
  const [showCreateTeam, setShowCreateTeam] = useState(false)
  const [showCreateManager, setShowCreateManager] = useState(false)
  const [showAddMember, setShowAddMember] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [teamForm, setTeamForm] = useState({
    name: '', description: '', domain_focus: [] as string[],
    region: 'India', timezone: 'Asia/Kolkata', manager_id: '', max_ticket_capacity: 20,
  })

  const [managerForm, setManagerForm] = useState({
    full_name: '', email: '', timezone: 'Asia/Kolkata', city: '', country: '',
  })

  const [memberForm, setMemberForm] = useState({
    engineer_id: '', role_in_team: 'member',
  })

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}`,
    'Content-Type': 'application/json',
  }), [])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [tR, mR] = await Promise.all([
        fetch(`${API}/api/v1/teams`, { headers: hdrs() }),
        fetch(`${API}/api/v1/teams/managers/list`, { headers: hdrs() }),
      ])
      if (tR.ok) setTeams(await tR.json())
      if (mR.ok) setManagers(await mR.json())
    } catch { }
    finally { setLoading(false) }
  }, [hdrs])

  useEffect(() => { fetchAll() }, [fetchAll])

  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(''), 3000); return () => clearTimeout(t) }
  }, [success])

  // ── Chat ───────────────────────────────────────────────────────────────────

  const connectChat = useCallback(async (team: Team) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setChatMessages([])
    setChatConnected(false)
    setOnlineCount(0)

    // Load history first
    try {
      const r = await fetch(`${API}/api/v1/teams/${team.team_id}/chat`, { headers: hdrs() })
      if (r.ok) {
        const history = await r.json()
        setChatMessages(history.map((m: any) => ({ ...m, type: 'message' })))
      }
    } catch { }

    // Connect WebSocket — token sent as first message, NOT in URL
    const ws = new WebSocket(`${WS_URL}/api/v1/teams/${team.team_id}/ws`)

    ws.onopen = () => {
      const token = sessionStorage.getItem('access_token') || ''
      ws.send(JSON.stringify({ type: 'auth', token }))
      setChatConnected(true)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.online_count !== undefined) setOnlineCount(msg.online_count)
        setChatMessages(prev => [...prev, msg])
      } catch { }
    }

    ws.onclose = () => {
      setChatConnected(false)
    }

    ws.onerror = () => {
      setChatConnected(false)
    }

    wsRef.current = ws
  }, [hdrs])

  // Connect chat when switching to chat tab
  useEffect(() => {
    if (detailTab === 'chat' && selected) {
      connectChat(selected)
    } else {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setChatConnected(false)
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [detailTab, selected?.team_id])

  // Auto scroll to bottom
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const sendMessage = () => {
    if (!chatInput.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(chatInput.trim())
    setChatInput('')
  }

  const handleChatKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const fmtTime = (s: string) => {
    const d = new Date(s)
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
  }

  const fmtDate = (s: string) => new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

  // ── Team actions ───────────────────────────────────────────────────────────

  const toggleDomain = (v: string) => {
    setTeamForm(f => ({
      ...f,
      domain_focus: f.domain_focus.includes(v)
        ? f.domain_focus.filter(d => d !== v)
        : [...f.domain_focus, v],
    }))
  }

  const submitCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!teamForm.name.trim()) { setError('Team name is required'); return }
    if (teamForm.domain_focus.length === 0) { setError('Select at least one domain'); return }
    setCreating(true)
    try {
      const payload: any = { ...teamForm }
      if (!payload.manager_id) delete payload.manager_id
      const r = await fetch(`${API}/api/v1/teams`, {
        method: 'POST', headers: hdrs(), body: JSON.stringify(payload),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Failed to create team')
      setSuccess(`Team ${d.team_id} created successfully`)
      setShowCreateTeam(false)
      setTeamForm({ name: '', description: '', domain_focus: [], region: 'India', timezone: 'Asia/Kolkata', manager_id: '', max_ticket_capacity: 20 })
      fetchAll()
    } catch (err: any) { setError(err.message) }
    finally { setCreating(false) }
  }

  const submitCreateManager = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!managerForm.full_name.trim() || !managerForm.email.trim()) { setError('Name and email required'); return }
    setCreating(true)
    try {
      const r = await fetch(`${API}/api/v1/teams/managers/create`, {
        method: 'POST', headers: hdrs(), body: JSON.stringify(managerForm),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Failed to create manager')
      setSuccess(`Manager ${d.full_name} created. Credentials sent via email.`)
      setShowCreateManager(false)
      setManagerForm({ full_name: '', email: '', timezone: 'Asia/Kolkata', city: '', country: '' })
      fetchAll()
    } catch (err: any) { setError(err.message) }
    finally { setCreating(false) }
  }

  const submitAddMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selected || !memberForm.engineer_id.trim()) { setError('Engineer ID required'); return }
    setCreating(true)
    setError('')
    try {
      const r = await fetch(`${API}/api/v1/teams/${selected.team_id}/members`, {
        method: 'POST', headers: hdrs(), body: JSON.stringify(memberForm),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Failed to add member')
      setSuccess('Member added successfully')
      setShowAddMember(false)
      setMemberForm({ engineer_id: '', role_in_team: 'member' })
      fetchAll()
      const updated = await fetch(`${API}/api/v1/teams/${selected.team_id}`, { headers: hdrs() })
      if (updated.ok) setSelected(await updated.json())
    } catch (err: any) { setError(err.message) }
    finally { setCreating(false) }
  }

  const removeMember = async (engineerId: string) => {
    if (!selected) return
    try {
      const r = await fetch(`${API}/api/v1/teams/${selected.team_id}/members/${engineerId}`, {
        method: 'DELETE', headers: hdrs(),
      })
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail) }
      setSuccess('Member removed')
      fetchAll()
      const updated = await fetch(`${API}/api/v1/teams/${selected.team_id}`, { headers: hdrs() })
      if (updated.ok) setSelected(await updated.json())
    } catch (err: any) { setError(err.message) }
  }

  const toggleTeamStatus = async (team: Team) => {
    const url = team.is_active
      ? `${API}/api/v1/teams/${team.team_id}`
      : `${API}/api/v1/teams/${team.team_id}/reactivate`
    const method = team.is_active ? 'DELETE' : 'POST'
    try {
      const r = await fetch(url, { method, headers: hdrs() })
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail) }
      setSuccess(team.is_active ? 'Team deactivated' : 'Team reactivated')
      fetchAll()
    } catch (err: any) { setError(err.message) }
  }

  const toggleManagerStatus = async (mgr: Manager) => {
    const url = mgr.is_active
      ? `${API}/api/v1/teams/managers/${mgr.id}`
      : `${API}/api/v1/teams/managers/${mgr.id}/reactivate`
    const method = mgr.is_active ? 'DELETE' : 'POST'
    try {
      const r = await fetch(url, { method, headers: hdrs() })
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail) }
      setSuccess(mgr.is_active ? 'Manager deactivated' : 'Manager reactivated')
      fetchAll()
    } catch (err: any) { setError(err.message) }
  }

  const filteredTeams = teams.filter(t => {
    if (search && !t.name.toLowerCase().includes(search.toLowerCase()) &&
      !t.team_id.toLowerCase().includes(search.toLowerCase())) return false
    if (regionFilter && t.region !== regionFilter) return false
    if (statusFilter === 'active' && !t.is_active) return false
    if (statusFilter === 'inactive' && t.is_active) return false
    return true
  })

  const availDot = (s: string) =>
    s === 'available' ? 'dot-ok' : s === 'busy' ? 'dot-warn' : 'dot-crit'

  const roleColor = (role: string) => {
    if (role === 'manager') return '#5b3d8a'
    if (role === 'admin') return '#4D1717'
    return '#174D38'
  }

  return (
    <>
      <style>{CSS}</style>
      <div className="tm" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: '-.01em' }}>Teams</div>
            <div className="small muted">Manage support teams, members and managers</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={fetchAll}>↻ Refresh</button>
            <button className="btn" onClick={() => { setShowCreateManager(true); setError('') }}>+ New Manager</button>
            <button className="btn btn-p" onClick={() => { setShowCreateTeam(true); setError('') }}>+ Create Team</button>
          </div>
        </div>

        {/* Banners */}
        {success && (
          <div style={{ padding: '10px 14px', background: '#e6f4ed', border: '1px solid #b7dfc8', borderRadius: 4, fontSize: 13, color: '#1a7a4a' }}>
            ✓ {success}
          </div>
        )}
        {error && !showCreateTeam && !showCreateManager && !showAddMember && (
          <div style={{ padding: '10px 14px', background: '#f5eaea', border: '1px solid #e8b4b4', borderRadius: 4, fontSize: 13, color: '#4D1717' }}>
            ✕ {error}
          </div>
        )}

        {/* Tabs */}
        <div className="tab" style={{ maxWidth: 300 }}>
          <button className={`tab-btn ${tab === 'teams' ? 'on' : ''}`} onClick={() => setTab('teams')}>
            Teams ({teams.length})
          </button>
          <button className={`tab-btn ${tab === 'managers' ? 'on' : ''}`} onClick={() => setTab('managers')}>
            Managers ({managers.length})
          </button>
        </div>

        {/* ── TEAMS TAB ── */}
        {tab === 'teams' && (
          <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 420px' : '1fr', gap: 12 }}>

            {/* Left */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="card" style={{ padding: '10px 14px' }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <input placeholder="Search teams..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200 }} />
                  <select value={regionFilter} onChange={e => setRegionFilter(e.target.value)} style={{ width: 140 }}>
                    <option value="">All Regions</option>
                    {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={{ width: 130 }}>
                    <option value="">All Status</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                  <span className="grow" />
                  <span className="small muted" style={{ alignSelf: 'center' }}>{filteredTeams.length} teams</span>
                </div>
              </div>

              <div className="card">
                <div className="c-head">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
                  <h3>All Teams</h3>
                </div>
                {loading ? (
                  <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>Loading...</div>
                ) : filteredTeams.length === 0 ? (
                  <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No teams found. Create your first team.</div>
                ) : (
                  <table className="dt">
                    <thead>
                      <tr>
                        <th>Team</th>
                        <th>Domains</th>
                        <th>Region</th>
                        <th>Manager</th>
                        <th>Members</th>
                        <th>Load</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTeams.map(team => (
                        <tr
                          key={team.id}
                          className={selected?.id === team.id ? 'sel' : ''}
                          onClick={() => { setSelected(selected?.id === team.id ? null : team); setDetailTab('info') }}
                        >
                          <td>
                            <div style={{ fontWeight: 600 }}>{team.name}</div>
                            <div className="tiny mono muted">{team.team_id}</div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', maxWidth: 160 }}>
                              {team.domain_focus.slice(0, 2).map(d => (
                                <span key={d} className="pill pill-grn" style={{ fontSize: 9 }}>
                                  {DOMAINS.find(x => x.v === d)?.l || d}
                                </span>
                              ))}
                              {team.domain_focus.length > 2 && (
                                <span className="pill" style={{ fontSize: 9 }}>+{team.domain_focus.length - 2}</span>
                              )}
                            </div>
                          </td>
                          <td><span className="small">{team.region}</span></td>
                          <td>{team.manager_name ? <span className="small">{team.manager_name}</span> : <span className="small muted">—</span>}</td>
                          <td><span className="pill pill-blue">{team.member_count} members</span></td>
                          <td>
                            <div style={{ width: 60 }}>
                              <div className="bar">
                                <div className="bar-f" style={{
                                  width: `${Math.min((team.active_ticket_count / team.max_ticket_capacity) * 100, 100)}%`,
                                  background: (team.active_ticket_count / team.max_ticket_capacity) > 0.8 ? '#4D1717' : '#174D38',
                                }} />
                              </div>
                              <div className="tiny muted mono" style={{ marginTop: 2 }}>{team.active_ticket_count}/{team.max_ticket_capacity}</div>
                            </div>
                          </td>
                          <td><span className={`pill ${team.is_active ? 'pill-ok' : 'pill-crit'}`}>{team.is_active ? 'Active' : 'Inactive'}</span></td>
                          <td onClick={e => e.stopPropagation()}>
                            <button className={`btn btn-sm ${team.is_active ? 'btn-r' : 'btn-p'}`} onClick={() => toggleTeamStatus(team)}>
                              {team.is_active ? 'Deactivate' : 'Reactivate'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Right — Detail panel */}
            {selected && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }} className="card">

                {/* Detail tabs */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', borderBottom: '1px solid #CBCBCB' }}>
                  <div className="detail-tabs" style={{ borderBottom: 'none' }}>
                    <button className={`detail-tab ${detailTab === 'info' ? 'on' : ''}`} onClick={() => setDetailTab('info')}>Info</button>
                    <button className={`detail-tab ${detailTab === 'members' ? 'on' : ''}`} onClick={() => setDetailTab('members')}>
                      Members ({selected.member_count})
                    </button>
                    <button className={`detail-tab ${detailTab === 'chat' ? 'on' : ''}`} onClick={() => setDetailTab('chat')}>
                      💬 Chat
                      {chatConnected && detailTab === 'chat' && (
                        <span style={{ marginLeft: 5 }}><span className="online-dot" /></span>
                      )}
                    </button>
                  </div>
                  <button className="btn btn-g btn-sm" onClick={() => setSelected(null)}>✕</button>
                </div>

                {/* INFO TAB */}
                {detailTab === 'info' && (
                  <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{selected.name}</div>
                      <span className={`pill ${selected.is_active ? 'pill-ok' : 'pill-crit'}`}>
                        {selected.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                      <div><div className="sec-lbl">Team ID</div><div className="mono small">{selected.team_id}</div></div>
                      <div><div className="sec-lbl">Region</div><div className="small">{selected.region}</div></div>
                      <div><div className="sec-lbl">Manager</div><div className="small">{selected.manager_name || '—'}</div></div>
                      <div><div className="sec-lbl">Timezone</div><div className="small mono">{selected.timezone}</div></div>
                      <div><div className="sec-lbl">Capacity</div><div className="small">{selected.active_ticket_count} / {selected.max_ticket_capacity}</div></div>
                      <div><div className="sec-lbl">Resolved</div><div className="small">{selected.total_resolved} tickets</div></div>
                    </div>
                    {selected.description && (
                      <div><div className="sec-lbl">Description</div><div className="small muted">{selected.description}</div></div>
                    )}
                    <div>
                      <div className="sec-lbl" style={{ marginBottom: 5 }}>Domain Focus</div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {selected.domain_focus.map(d => (
                          <span key={d} className="pill pill-grn">{DOMAINS.find(x => x.v === d)?.l || d}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* MEMBERS TAB */}
                {detailTab === 'members' && (
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #f0f0f0' }}>
                      <span className="small muted">{selected.member_count} engineer{selected.member_count !== 1 ? 's' : ''} — cross-domain team</span>
                      <button className="btn btn-p btn-sm" onClick={() => { setShowAddMember(true); setError('') }}>+ Add Member</button>
                    </div>
                    {selected.members.length === 0 ? (
                      <div style={{ padding: 24, textAlign: 'center', color: '#6b6b6b', fontSize: 12 }}>
                        No members yet. Add engineers to this team.
                      </div>
                    ) : (
                      <table className="dt">
                        <thead>
                          <tr>
                            <th>Engineer</th>
                            <th>Domains</th>
                            <th>Status</th>
                            <th>Role</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.members.map(m => (
                            <tr key={m.id} style={{ cursor: 'default' }}>
                              <td>
                                <div style={{ fontWeight: 500 }}>{m.full_name}</div>
                                <div className="tiny mono muted">{m.engineer_id}</div>
                              </td>
                              <td>
                                <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                                  {m.domain_expertise.slice(0, 2).map(d => (
                                    <span key={d} className="pill" style={{ fontSize: 9 }}>{DOMAINS.find(x => x.v === d)?.l || d}</span>
                                  ))}
                                  {m.domain_expertise.length > 2 && (
                                    <span className="pill" style={{ fontSize: 9 }}>+{m.domain_expertise.length - 2}</span>
                                  )}
                                </div>
                              </td>
                              <td>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                  <span className={`dot ${availDot(m.availability_status || '')}`} />
                                  <span className="small">{m.availability_status || '—'}</span>
                                </div>
                              </td>
                              <td><span className={`pill ${m.role_in_team === 'lead' ? 'pill-pur' : ''}`}>{m.role_in_team}</span></td>
                              <td><button className="btn btn-sm btn-r" onClick={() => removeMember(m.engineer_id)}>Remove</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}

                {/* CHAT TAB */}
                {detailTab === 'chat' && (
                  <div className="chat-wrap">
                    {/* Chat header */}
                    <div style={{ padding: '8px 14px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 8, background: '#fff' }}>
                      <span className="online-dot" style={{ background: chatConnected ? '#1a7a4a' : '#CBCBCB', boxShadow: chatConnected ? '0 0 4px #1a7a4a' : 'none' }} />
                      <span className="small" style={{ color: chatConnected ? '#1a7a4a' : '#6b6b6b' }}>
                        {chatConnected ? `Connected · ${onlineCount} online` : 'Connecting...'}
                      </span>
                      <span className="grow" />
                      <span className="tiny muted">{selected.name} · Team Chat</span>
                    </div>

                    {/* Messages */}
                    <div className="chat-msgs">
                      {chatMessages.length === 0 && (
                        <div style={{ textAlign: 'center', color: '#6b6b6b', fontSize: 12, marginTop: 40 }}>
                          No messages yet. Start the conversation!
                        </div>
                      )}
                      {chatMessages.map((msg, i) => {
                        const isMe = msg.sender_id === currentUserId
                        const isSystem = msg.type === 'system'
                        return (
                          <div key={msg.id || i} className={`chat-msg ${isSystem ? 'system' : isMe ? 'mine' : 'other'}`}>
                            {!isSystem && !isMe && (
                              <div className="chat-meta" style={{ color: roleColor(msg.sender_role) }}>
                                {msg.sender_name} · {msg.sender_role}
                              </div>
                            )}
                            <div className={`chat-bubble ${isSystem ? 'system' : isMe ? 'mine' : 'other'}`}>
                              {msg.message}
                            </div>
                            {!isSystem && (
                              <div className="chat-meta">{fmtTime(msg.timestamp)}</div>
                            )}
                          </div>
                        )
                      })}
                      <div ref={chatBottomRef} />
                    </div>

                    {/* Input */}
                    <div className="chat-input-wrap">
                      <input
                        className="chat-input"
                        placeholder={chatConnected ? 'Message the team...' : 'Connecting...'}
                        value={chatInput}
                        onChange={e => setChatInput(e.target.value)}
                        onKeyDown={handleChatKeyDown}
                        disabled={!chatConnected}
                      />
                      <button
                        className="chat-send"
                        onClick={sendMessage}
                        disabled={!chatConnected || !chatInput.trim()}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <line x1="22" y1="2" x2="11" y2="13" />
                          <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── MANAGERS TAB ── */}
        {tab === 'managers' && (
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
              <h3>Managers</h3>
            </div>
            {managers.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No managers yet. Create your first manager.</div>
            ) : (
              <table className="dt">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Location</th>
                    <th>Timezone</th>
                    <th>Teams Managed</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {managers.map(mgr => (
                    <tr key={mgr.id} style={{ cursor: 'default' }}>
                      <td style={{ fontWeight: 500 }}>{mgr.full_name}</td>
                      <td className="small muted">{mgr.email}</td>
                      <td className="small">{[mgr.city, mgr.country].filter(Boolean).join(', ') || '—'}</td>
                      <td className="small mono">{mgr.timezone || '—'}</td>
                      <td>
                        {mgr.teams.length === 0
                          ? <span className="muted small">No teams</span>
                          : <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {mgr.teams.map(t => <span key={t} className="pill pill-grn">{t}</span>)}
                          </div>
                        }
                      </td>
                      <td><span className={`pill ${mgr.is_active ? 'pill-ok' : 'pill-crit'}`}>{mgr.is_active ? 'Active' : 'Inactive'}</span></td>
                      <td>
                        <button className={`btn btn-sm ${mgr.is_active ? 'btn-r' : 'btn-p'}`} onClick={() => toggleManagerStatus(mgr)}>
                          {mgr.is_active ? 'Deactivate' : 'Reactivate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* ── CREATE TEAM MODAL ── */}
        {showCreateTeam && (
          <div className="overlay" onClick={() => setShowCreateTeam(false)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-head">
                <h2>Create New Team</h2>
                <button className="btn btn-g btn-sm" onClick={() => setShowCreateTeam(false)}>✕</button>
              </div>
              <form onSubmit={submitCreateTeam}>
                <div className="modal-body">
                  {error && <div style={{ padding: '8px 12px', background: '#f5eaea', borderRadius: 4, fontSize: 12, color: '#4D1717' }}>{error}</div>}
                  <div>
                    <label className="lbl">Team Name *</label>
                    <input placeholder="e.g. Alpha Support Team" value={teamForm.name} onChange={e => setTeamForm(f => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="lbl">Description</label>
                    <textarea rows={2} placeholder="Brief description..." value={teamForm.description} onChange={e => setTeamForm(f => ({ ...f, description: e.target.value }))} />
                  </div>
                  <div>
                    <label className="lbl">Domain Focus * (select all that apply)</label>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                      {DOMAINS.map(d => (
                        <span key={d.v} className={`chip ${teamForm.domain_focus.includes(d.v) ? 'on' : ''}`} onClick={() => toggleDomain(d.v)}>{d.l}</span>
                      ))}
                    </div>
                    {teamForm.domain_focus.length > 0 && <div className="tiny muted" style={{ marginTop: 5 }}>{teamForm.domain_focus.length} domain(s) selected</div>}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <label className="lbl">Region *</label>
                      <select value={teamForm.region} onChange={e => setTeamForm(f => ({ ...f, region: e.target.value }))}>
                        {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="lbl">Timezone *</label>
                      <select value={teamForm.timezone} onChange={e => setTeamForm(f => ({ ...f, timezone: e.target.value }))}>
                        {TIMEZONES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <label className="lbl">Assign Manager (optional)</label>
                      <select value={teamForm.manager_id} onChange={e => setTeamForm(f => ({ ...f, manager_id: e.target.value }))}>
                        <option value="">— No manager yet —</option>
                        {managers.filter(m => m.is_active).map(m => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="lbl">Max Ticket Capacity</label>
                      <input type="number" min={1} max={200} value={teamForm.max_ticket_capacity} onChange={e => setTeamForm(f => ({ ...f, max_ticket_capacity: parseInt(e.target.value) }))} />
                    </div>
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn" onClick={() => setShowCreateTeam(false)}>Cancel</button>
                  <button type="submit" className="btn btn-p" disabled={creating}>{creating ? 'Creating...' : 'Create Team ✓'}</button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── CREATE MANAGER MODAL ── */}
        {showCreateManager && (
          <div className="overlay" onClick={() => setShowCreateManager(false)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-head">
                <h2>Create New Manager</h2>
                <button className="btn btn-g btn-sm" onClick={() => setShowCreateManager(false)}>✕</button>
              </div>
              <form onSubmit={submitCreateManager}>
                <div className="modal-body">
                  {error && <div style={{ padding: '8px 12px', background: '#f5eaea', borderRadius: 4, fontSize: 12, color: '#4D1717' }}>{error}</div>}
                  <div style={{ padding: '10px 12px', background: '#e8f2ed', borderRadius: 4, fontSize: 12, color: '#174D38' }}>
                    ℹ A temporary password will be emailed to the manager.
                  </div>
                  <div>
                    <label className="lbl">Full Name *</label>
                    <input placeholder="e.g. John Smith" value={managerForm.full_name} onChange={e => setManagerForm(f => ({ ...f, full_name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="lbl">Email *</label>
                    <input type="email" placeholder="manager@company.com" value={managerForm.email} onChange={e => setManagerForm(f => ({ ...f, email: e.target.value }))} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <div>
                      <label className="lbl">City</label>
                      <input placeholder="e.g. Pune" value={managerForm.city} onChange={e => setManagerForm(f => ({ ...f, city: e.target.value }))} />
                    </div>
                    <div>
                      <label className="lbl">Country</label>
                      <input placeholder="e.g. India" value={managerForm.country} onChange={e => setManagerForm(f => ({ ...f, country: e.target.value }))} />
                    </div>
                  </div>
                  <div>
                    <label className="lbl">Timezone</label>
                    <select value={managerForm.timezone} onChange={e => setManagerForm(f => ({ ...f, timezone: e.target.value }))}>
                      {TIMEZONES.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn" onClick={() => setShowCreateManager(false)}>Cancel</button>
                  <button type="submit" className="btn btn-p" disabled={creating}>{creating ? 'Creating...' : 'Create Manager ✓'}</button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── ADD MEMBER MODAL ── */}
        {showAddMember && selected && (
          <div className="overlay" onClick={() => setShowAddMember(false)}>
            <div className="modal" style={{ width: 400 }} onClick={e => e.stopPropagation()}>
              <div className="modal-head">
                <h2>Add Member to {selected.name}</h2>
                <button className="btn btn-g btn-sm" onClick={() => setShowAddMember(false)}>✕</button>
              </div>
              <form onSubmit={submitAddMember}>
                <div className="modal-body">
                  {error && <div style={{ padding: '8px 12px', background: '#f5eaea', borderRadius: 4, fontSize: 12, color: '#4D1717' }}>{error}</div>}
                  <div style={{ padding: '10px 12px', background: '#e8f2ed', borderRadius: 4, fontSize: 12, color: '#174D38' }}>
                    ℹ Engineers can be from any domain. Teams support cross-domain members.
                  </div>
                  <div>
                    <label className="lbl">Engineer ID *</label>
                    <input placeholder="e.g. ENG-1234" value={memberForm.engineer_id} onChange={e => setMemberForm(f => ({ ...f, engineer_id: e.target.value.toUpperCase() }))} />
                  </div>
                  <div>
                    <label className="lbl">Role in Team</label>
                    <select value={memberForm.role_in_team} onChange={e => setMemberForm(f => ({ ...f, role_in_team: e.target.value }))}>
                      <option value="member">Member</option>
                      <option value="lead">Lead</option>
                    </select>
                  </div>
                </div>
                <div className="modal-foot">
                  <button type="button" className="btn" onClick={() => setShowAddMember(false)}>Cancel</button>
                  <button type="submit" className="btn btn-p" disabled={creating}>{creating ? 'Adding...' : 'Add Member ✓'}</button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </>
  )
}