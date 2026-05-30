// Location: ./frontend/src/app/manager/chat/page.tsx
'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

const API    = process.env.NEXT_PUBLIC_API_URL
const WS_URL = process.env.NEXT_PUBLIC_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'

interface ChatMessage {
  id: string; message: string; sender_id: string
  sender_name: string; sender_role: string
  timestamp: string; type?: 'message' | 'system'; online_count?: number
}

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
  .mc *{box-sizing:border-box}
  .mc{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414}
  .mc .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
  .mc .mono{font-family:"JetBrains Mono",monospace}
  .mc .muted{color:#6b6b6b}
  .mc .small{font-size:11px}
  .mc .tiny{font-size:10px}
  .mc .chat-header{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px;background:#fff;border-radius:6px 6px 0 0}
  .mc .chat-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#FAFAFA}
  .mc .msg{display:flex;flex-direction:column;max-width:72%}
  .mc .msg.mine{align-self:flex-end;align-items:flex-end}
  .mc .msg.other{align-self:flex-start;align-items:flex-start}
  .mc .msg.system{align-self:center;align-items:center}
  .mc .bubble{padding:8px 12px;border-radius:8px;font-size:12px;line-height:1.5;word-break:break-word}
  .mc .bubble.mine{background:#174D38;color:#fff;border-radius:8px 8px 2px 8px}
  .mc .bubble.other{background:#fff;border:1px solid #CBCBCB;color:#141414;border-radius:8px 8px 8px 2px}
  .mc .bubble.manager-msg{background:#f0edf8;border:1px solid #d4c9f0;color:#3a2060;border-radius:8px 8px 8px 2px}
  .mc .bubble.system{background:transparent;color:#6b6b6b;font-size:11px;font-style:italic;padding:2px 8px;border:none}
  .mc .meta{font-size:10px;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-bottom:3px}
  .mc .timestamp{font-size:10px;color:#a0a0a0;font-family:"JetBrains Mono",monospace;margin-top:3px}
  .mc .input-wrap{padding:10px 14px;border-top:1px solid #CBCBCB;display:flex;gap:8px;align-items:center;background:#fff;border-radius:0 0 6px 6px}
  .mc .chat-input{flex:1;padding:8px 14px;background:#F2F2F2;border:1px solid #CBCBCB;color:#141414;font-family:inherit;font-size:13px;outline:none;border-radius:20px;transition:border-color .15s}
  .mc .chat-input:focus{border-color:#174D38;background:#fff}
  .mc .chat-input::placeholder{color:#a0a0a0}
  .mc .send-btn{width:34px;height:34px;border-radius:50%;background:#174D38;border:none;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s}
  .mc .send-btn:hover{background:#1f6347}
  .mc .send-btn:disabled{background:#CBCBCB;cursor:not-allowed}
  .mc .online-dot{width:7px;height:7px;border-radius:50%;background:#1a7a4a;box-shadow:0 0 4px #1a7a4a;display:inline-block}
  .mc .pill{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB}
  .mc .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
  .mc .pill-pur{background:#f0edf8;color:#5b3d8a;border-color:transparent}
`

export default function ManagerChatPage() {
  const [teamId,    setTeamId]    = useState('')
  const [teamName,  setTeamName]  = useState('')
  const [members,   setMembers]   = useState<any[]>([])
  const [messages,  setMessages]  = useState<ChatMessage[]>([])
  const [input,     setInput]     = useState('')
  const [connected, setConnected] = useState(false)
  const [onlineCount, setOnlineCount] = useState(0)
  const [loading,   setLoading]   = useState(true)

  const wsRef     = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const currentUserId = typeof window !== 'undefined' ? localStorage.getItem('user_id') || '' : ''

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  }), [])

  useEffect(() => {
    fetch(`${API}/api/v1/manager/my-team`, { headers: hdrs() })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.team_id) { setTeamId(d.team_id); setTeamName(d.name) }
        if (d?.members) setMembers(d.members)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [hdrs])

  useEffect(() => {
    if (!teamId) return

    fetch(`${API}/api/v1/teams/${teamId}/chat`, { headers: hdrs() })
      .then(r => r.ok ? r.json() : [])
      .then(history => setMessages(history.map((m: any) => ({ ...m, type: 'message' }))))
      .catch(() => {})

    const token = localStorage.getItem('access_token') || ''
    const ws = new WebSocket(`${WS_URL}/api/v1/teams/${teamId}/ws?token=${token}`)
    ws.onopen    = () => setConnected(true)
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.online_count !== undefined) setOnlineCount(msg.online_count)
        setMessages(prev => [...prev, msg])
      } catch { }
    }
    ws.onclose  = () => setConnected(false)
    ws.onerror  = () => setConnected(false)
    wsRef.current = ws

    return () => { ws.close(); wsRef.current = null }
  }, [teamId, hdrs])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(input.trim())
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const fmtTime = (s: string) =>
    new Date(s).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })

  const roleColor = (role: string) => {
    if (role === 'manager') return '#5b3d8a'
    if (role === 'admin')   return '#4D1717'
    return '#174D38'
  }

  const getBubbleClass = (msg: ChatMessage) => {
    if (msg.type === 'system') return 'system'
    if (msg.sender_id === currentUserId) return 'mine'
    if (msg.sender_role === 'manager') return 'manager-msg'
    return 'other'
  }

  if (loading) return (
    <>
      <style>{CSS}</style>
      <div className="mc" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>Loading...</div>
    </>
  )

  if (!teamId) return (
    <>
      <style>{CSS}</style>
      <div className="mc" style={{ padding: 40, textAlign: 'center', color: '#6b6b6b' }}>No team assigned. Contact your admin.</div>
    </>
  )

  return (
    <>
      <style>{CSS}</style>
      <div className="mc" style={{ display: 'grid', gridTemplateColumns: '1fr 220px', gap: 12, height: 'calc(100vh - 120px)' }}>

        {/* Chat panel */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* Header */}
          <div className="chat-header">
            <span className="online-dot" style={{ background: connected ? '#1a7a4a' : '#CBCBCB', boxShadow: connected ? '0 0 4px #1a7a4a' : 'none' }}/>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 12 }}>{teamName} · Team Chat</div>
              <div style={{ fontSize: 10, color: connected ? '#1a7a4a' : '#6b6b6b', fontFamily: '"JetBrains Mono",monospace' }}>
                {connected ? `${onlineCount} online` : 'Connecting...'}
              </div>
            </div>
            <span style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace' }}>
              {messages.filter(m => m.type !== 'system').length} messages
            </span>
          </div>

          {/* Messages */}
          <div className="chat-msgs">
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: '#6b6b6b', fontSize: 12, marginTop: 60 }}>
                No messages yet. Start the conversation with your team!
              </div>
            )}
            {messages.map((msg, i) => {
              const isMe     = msg.sender_id === currentUserId
              const isSystem = msg.type === 'system'
              return (
                <div key={msg.id || i} className={`msg ${isSystem ? 'system' : isMe ? 'mine' : 'other'}`}>
                  {!isSystem && !isMe && (
                    <div className="meta" style={{ color: roleColor(msg.sender_role) }}>
                      {msg.sender_name} · {msg.sender_role}
                    </div>
                  )}
                  <div className={`bubble ${getBubbleClass(msg)}`}>{msg.message}</div>
                  {!isSystem && <div className="timestamp">{fmtTime(msg.timestamp)}</div>}
                </div>
              )
            })}
            <div ref={bottomRef}/>
          </div>

          {/* Input */}
          <div className="input-wrap">
            <input
              className="chat-input"
              placeholder={connected ? `Message ${teamName}...` : 'Connecting...'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!connected}
            />
            <button className="send-btn" onClick={sendMessage} disabled={!connected || !input.trim()}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Members sidebar */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid #CBCBCB', fontSize: 12, fontWeight: 600 }}>
            Members ({members.length})
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {members.map(m => (
              <div key={m.id} style={{ padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #f0f0f0' }}>
                <div style={{ width: 28, height: 28, borderRadius: 4, background: '#174D38', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                  {m.full_name?.charAt(0)}
                </div>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.full_name}</div>
                  <div style={{ fontSize: 10, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace' }}>{m.engineer_id}</div>
                </div>
                <div style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: m.availability_status === 'available' ? '#1a7a4a' : m.availability_status === 'busy' ? '#8a5a00' : '#CBCBCB' }}/>
              </div>
            ))}
          </div>
        </div>

      </div>
    </>
  )
}