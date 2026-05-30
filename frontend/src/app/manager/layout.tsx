// Location: ./frontend/src/app/manager/layout.tsx
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/manager/overview', label: 'Overview',       icon: '⬡' },
  { href: '/manager/team',     label: 'My Team',        icon: '◈' },
  { href: '/manager/tickets',  label: 'Ticket Queue',   icon: '◎' },
  { href: '/manager/chat',     label: 'Team Chat',      icon: '◉' },
  { href: '/manager/knowledge',label: 'Knowledge Base', icon: '◆' },
]

export default function ManagerLayout({ children }: { children: React.ReactNode }) {
  const pathname  = usePathname()
  const [fullName, setFullName] = useState('Manager')
  const [teamName, setTeamName] = useState('')
  const [teamId,   setTeamId]   = useState('')
  const [mounted,  setMounted]  = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const API = process.env.NEXT_PUBLIC_API_URL

  useEffect(() => {
    setMounted(true)
    const role = localStorage.getItem('role')
    const name = localStorage.getItem('full_name')
    if (role !== 'manager') window.location.replace('/auth/login')
    if (name) setFullName(name)

    const token = localStorage.getItem('access_token')
    fetch(`${API}/api/v1/manager/my-team`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.name)    setTeamName(d.name)
        if (d?.team_id) setTeamId(d.team_id)
      })
      .catch(() => {})
  }, [])

  const handleLogout = () => {
    localStorage.clear()
    window.location.replace('/auth/login')
  }

  const sidebarW = collapsed ? 64 : 240

  if (!mounted) return null

  return (
    <div style={{
      display: 'flex', minHeight: '100vh',
      background: '#F2F2F2',
      fontFamily: '"Inter", -apple-system, sans-serif',
      color: '#141414',
    }}>
      {/* Sidebar */}
      <aside style={{
        width: sidebarW, flexShrink: 0,
        background: '#fff',
        borderRight: '1px solid #CBCBCB',
        display: 'flex', flexDirection: 'column',
        position: 'fixed', top: 0, left: 0, bottom: 0,
        zIndex: 50, transition: 'width 0.25s ease',
        overflow: 'hidden',
        boxShadow: '1px 0 0 #CBCBCB',
      }}>
        {/* Logo */}
        <div style={{
          height: 56, display: 'flex', alignItems: 'center',
          padding: collapsed ? '0' : '0 18px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: 10, borderBottom: '1px solid #CBCBCB', flexShrink: 0,
        }}>
          <svg width="26" height="26" viewBox="0 0 32 32" style={{ flexShrink: 0 }}>
            <polygon points="16,2 30,9 30,23 16,30 2,23 2,9" fill="#174D38"/>
            <circle cx="16" cy="16" r="4" fill="#4d9e78"/>
          </svg>
          {!collapsed && (
            <div>
              <div style={{ fontFamily: 'Georgia, serif', fontSize: 16, fontWeight: 600, color: '#141414', whiteSpace: 'nowrap', lineHeight: 1.2 }}>NexusDesk</div>
              <div style={{ fontSize: 9, fontFamily: '"JetBrains Mono", monospace', color: '#6b6b6b', textTransform: 'uppercase', letterSpacing: '.08em' }}>Manager Panel</div>
            </div>
          )}
        </div>

        {/* User info */}
        {!collapsed && (
          <div style={{ padding: '12px 18px', borderBottom: '1px solid #CBCBCB', flexShrink: 0, background: '#FAFAFA' }}>
            <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', marginBottom: 3 }}>Signed in as</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#141414', marginBottom: 2 }}>{fullName}</div>
            {teamName && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#174D38' }}/>
                <span style={{ fontSize: 11, color: '#174D38', fontWeight: 500 }}>{teamName}</span>
                <span style={{ fontSize: 10, fontFamily: '"JetBrains Mono",monospace', color: '#6b6b6b' }}>{teamId}</span>
              </div>
            )}
          </div>
        )}

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 0', overflowY: 'auto' }}>
          {navItems.map(item => {
            const active = pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link key={item.href} href={item.href} style={{
                display: 'flex', alignItems: 'center',
                gap: 10, padding: collapsed ? '10px 0' : '8px 18px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                height: 38, fontSize: 13,
                color: active ? '#174D38' : '#6b6b6b',
                textDecoration: 'none',
                background: active ? 'rgba(23,77,56,0.07)' : 'transparent',
                borderLeft: active ? '2px solid #174D38' : '2px solid transparent',
                fontWeight: active ? 600 : 400,
                transition: 'all 0.15s',
              }}>
                <span style={{ fontSize: 13, flexShrink: 0, color: active ? '#174D38' : '#a0a0a0' }}>{item.icon}</span>
                {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Bottom */}
        <div style={{ padding: collapsed ? '10px 0' : '10px 18px', borderTop: '1px solid #CBCBCB', flexShrink: 0 }}>
          <button
            onClick={() => setCollapsed(c => !c)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6b6b6b', cursor: 'pointer', fontSize: 12, padding: '4px 0', width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', fontFamily: 'inherit' }}
          >
            <span>{collapsed ? '→' : '←'}</span>
            {!collapsed && <span>Collapse</span>}
          </button>
          {!collapsed && (
            <button
              onClick={handleLogout}
              style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6b6b6b', cursor: 'pointer', fontSize: 12, padding: '4px 0', marginTop: 4, width: '100%', fontFamily: 'inherit' }}
            >
              <span>⎋</span><span>Sign Out</span>
            </button>
          )}
        </div>
      </aside>

      {/* Main */}
      <main style={{ marginLeft: sidebarW, flex: 1, display: 'flex', flexDirection: 'column', transition: 'margin-left 0.25s ease', minHeight: '100vh' }}>
        {/* Topbar */}
        <div style={{
          height: 56, background: '#fff',
          borderBottom: '1px solid #CBCBCB',
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px', position: 'sticky', top: 0, zIndex: 40,
          flexShrink: 0,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#141414', letterSpacing: '-.01em' }}>
            {navItems.find(n => pathname === n.href || pathname.startsWith(n.href + '/'))?.label || 'Manager Panel'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#1a7a4a', boxShadow: '0 0 5px #1a7a4a' }}/>
            <span style={{ fontSize: 11, color: '#6b6b6b', fontFamily: '"JetBrains Mono",monospace', letterSpacing: '.04em' }}>System Online</span>
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: '20px 24px', flex: 1 }}>
          {children}
        </div>
      </main>
    </div>
  )
}