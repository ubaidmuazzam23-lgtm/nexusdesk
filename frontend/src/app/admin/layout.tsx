'use client'
// File: frontend/src/app/admin/layout.tsx

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/admin/overview',       label: 'Overview',       icon: '▣' },
  { href: '/admin/knowledge-base', label: 'Knowledge Base', icon: '◫' },
  { href: '/admin/assets',         label: 'Assets',         icon: '◈' },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname   = usePathname()
  const [fullName, setFullName]   = useState('Admin')
  const [dark,     setDark]       = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [mounted,  setMounted]    = useState(false)

  useEffect(() => {
    setMounted(true)
    const name = sessionStorage.getItem('full_name')
    const role = sessionStorage.getItem('role')
    const savedTheme = localStorage.getItem('admin_theme')
    if (role !== 'admin') window.location.replace('/auth/login')
    if (name) setFullName(name)
    if (savedTheme) setDark(savedTheme === 'dark')
  }, [])

  const toggleTheme = () => {
    const next = !dark
    setDark(next)
    localStorage.setItem('admin_theme', next ? 'dark' : 'light')
  }

  const handleLogout = () => {
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('refresh_token')
    sessionStorage.removeItem('role')
    sessionStorage.removeItem('full_name')
    sessionStorage.removeItem('email')
    sessionStorage.removeItem('user_id')
    window.location.replace('/auth/login')
  }

  const t = {
    bg:        dark ? '#0a0a0a'                  : '#f2f2f2',
    sidebar:   dark ? '#0f0f0f'                  : '#ffffff',
    topbar:    dark ? '#0f0f0f'                  : '#ffffff',
    border:    dark ? 'rgba(255,255,255,0.07)'   : '#e0e0e0',
    text:      dark ? '#F2F2F2'                  : '#111111',
    textMuted: dark ? 'rgba(242,242,242,0.4)'    : '#888888',
    navHover:  dark ? 'rgba(255,255,255,0.04)'   : 'rgba(0,0,0,0.04)',
    navActive: dark ? 'rgba(23,77,56,0.15)'      : 'rgba(23,77,56,0.06)',
  }

  const sidebarW = collapsed ? 56 : 220

  if (!mounted) return null

  return (
    <div style={{
      display: 'flex', minHeight: '100vh',
      background: t.bg,
      fontFamily: "'IBM Plex Sans', 'Helvetica Neue', sans-serif",
      color: t.text,
      transition: 'background 0.2s, color 0.2s',
    }}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');`}</style>

      {/* ── Sidebar ── */}
      <aside style={{
        width: sidebarW, flexShrink: 0,
        background: t.sidebar,
        borderRight: `1px solid ${t.border}`,
        display: 'flex', flexDirection: 'column',
        position: 'fixed', top: 0, left: 0, bottom: 0,
        zIndex: 50, transition: 'width 0.2s ease',
        overflow: 'hidden',
      }}>

        {/* Logo */}
        <div style={{
          height: 56, display: 'flex', alignItems: 'center',
          padding: collapsed ? '0 16px' : '0 20px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: 10, borderBottom: `1px solid ${t.border}`, flexShrink: 0,
        }}>
          {/* 4-square mark */}
          <div style={{
            width: 24, height: 24, flexShrink: 0,
            display: 'grid', gridTemplateColumns: '1fr 1fr',
            gap: 2, padding: 3,
            border: `1px solid ${dark ? 'rgba(23,77,56,0.6)' : '#174D38'}`,
          }}>
            <div style={{ background: '#4d9e78' }}/>
            <div style={{ background: '#174D38' }}/>
            <div style={{ background: '#174D38' }}/>
            <div style={{ background: '#4d9e78' }}/>
          </div>
          {!collapsed && (
            <div>
              <div style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 13, fontWeight: 600,
                color: t.text, whiteSpace: 'nowrap',
                letterSpacing: '0.01em',
              }}>
                TestSoftware
              </div>
              <div style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 8, color: '#174D38',
                letterSpacing: '0.14em', textTransform: 'uppercase',
                marginTop: 1,
              }}>
                Admin Console
              </div>
            </div>
          )}
        </div>

        {/* User info */}
        {!collapsed && (
          <div style={{
            padding: '12px 20px',
            borderBottom: `1px solid ${t.border}`,
            flexShrink: 0,
          }}>
            <div style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 9, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: t.textMuted, marginBottom: 3,
            }}>
              Signed in as
            </div>
            <div style={{ fontSize: 13, fontWeight: 500, color: t.text, marginBottom: 6 }}>
              {fullName}
            </div>
            <div style={{
              display: 'inline-block', fontSize: 9, padding: '2px 7px',
              background: 'rgba(77,23,23,0.1)', border: '1px solid rgba(77,23,23,0.2)',
              color: '#a04040', letterSpacing: '0.1em', textTransform: 'uppercase',
              fontFamily: "'IBM Plex Mono', monospace",
            }}>
              Super Admin
            </div>
          </div>
        )}

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 0' }}>
          {navItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  display: 'flex', alignItems: 'center',
                  gap: 10,
                  padding: collapsed ? '10px 0' : '9px 20px',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  textDecoration: 'none',
                  background: active ? t.navActive : 'transparent',
                  borderLeft: active ? '2px solid #174D38' : '2px solid transparent',
                  color: active ? '#174D38' : t.textMuted,
                  fontSize: 13, fontWeight: active ? 600 : 400,
                  transition: 'all 0.12s', marginBottom: 1,
                }}
                onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.background = t.navHover }}
                onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
              >
                <span style={{ fontSize: 13, flexShrink: 0, opacity: active ? 1 : 0.6 }}>{item.icon}</span>
                {!collapsed && (
                  <span style={{ whiteSpace: 'nowrap', fontFamily: "'IBM Plex Sans', sans-serif" }}>
                    {item.label}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        {/* Bottom buttons */}
        <div style={{ borderTop: `1px solid ${t.border}`, padding: '6px 0', flexShrink: 0 }}>
          {[
            { icon: dark ? '☀' : '◑', label: dark ? 'Light Mode' : 'Dark Mode', action: toggleTheme,                        color: t.textMuted },
            { icon: collapsed ? '→' : '←', label: collapsed ? 'Expand' : 'Collapse', action: () => setCollapsed(c => !c), color: t.textMuted },
            { icon: '⏻',                  label: 'Sign Out',                          action: handleLogout,                    color: '#a04040'    },
          ].map((btn, i) => (
            <button key={i} onClick={btn.action} style={{
              display: 'flex', alignItems: 'center',
              gap: 10, padding: collapsed ? '9px 0' : '9px 20px',
              justifyContent: collapsed ? 'center' : 'flex-start',
              width: '100%', background: 'none', border: 'none',
              color: btn.color, fontSize: 13, cursor: 'pointer',
              transition: 'background 0.12s',
              fontFamily: "'IBM Plex Sans', sans-serif",
            }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = i === 2 ? 'rgba(77,23,23,0.08)' : t.navHover}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
            >
              <span style={{ fontSize: 13, flexShrink: 0 }}>{btn.icon}</span>
              {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{btn.label}</span>}
            </button>
          ))}
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{
        flex: 1,
        marginLeft: sidebarW,
        transition: 'margin-left 0.2s ease',
        minHeight: '100vh',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Topbar */}
        <div style={{
          height: 48,
          background: t.topbar,
          borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 28px',
          position: 'sticky', top: 0, zIndex: 40,
          flexShrink: 0,
        }}>
          <div style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 12, fontWeight: 500, color: t.text,
            letterSpacing: '0.01em',
          }}>
            {navItems.find(n => pathname === n.href || pathname.startsWith(n.href + '/'))?.label || 'Admin'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 5px #22c55e' }}/>
            <span style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 10, color: t.textMuted, letterSpacing: '0.06em',
            }}>
              System online
            </span>
          </div>
        </div>

        {/* Page content */}
        <div style={{ padding: '24px 28px', flex: 1 }}>
          {children}
        </div>
      </main>
    </div>
  )
}