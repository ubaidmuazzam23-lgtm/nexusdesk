'use client'
// File: frontend/src/app/auth/login/page.tsx

import { useState, useEffect } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

export default function LoginPage() {
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [mounted,  setMounted]  = useState(false)

  useEffect(() => {
    setMounted(true)
    document.documentElement.style.background = '#f0f0f0'
    document.body.style.background = '#f0f0f0'
    document.body.style.margin = '0'
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await fetch(`${API}/api/v1/auth/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email, password }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Invalid credentials')
      if (d.role !== 'admin') throw new Error('Access restricted to administrators')
      sessionStorage.setItem('access_token',  d.access_token)
      sessionStorage.setItem('refresh_token', d.refresh_token)
      sessionStorage.setItem('role',          d.role)
      sessionStorage.setItem('full_name',     d.full_name)
      sessionStorage.setItem('email',         d.email)
      if (d.user_id) sessionStorage.setItem('user_id', d.user_id)
      window.location.replace('/admin/overview')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!mounted) return null

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: '#efefef',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: "'IBM Plex Sans', 'Helvetica Neue', sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: #bbb !important; }
      `}</style>

      {/* Card */}
      <div style={{
        position: 'relative', zIndex: 1,
        width: '100%', maxWidth: 420,
        background: '#ffffff',
        border: '1px solid #d8d8d8',
        boxShadow: '0 8px 48px rgba(0,0,0,0.13), 0 2px 8px rgba(0,0,0,0.07)',
      }}>
        {/* Top accent */}
        <div style={{ height: 3, background: '#174D38' }}/>

        <div style={{ padding: '44px 44px 48px' }}>

          {/* Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 40 }}>
            <div style={{
              width: 36, height: 36,
              border: '1.5px solid #174D38',
              display: 'grid', gridTemplateColumns: '1fr 1fr',
              gap: 3, padding: 6, flexShrink: 0,
            }}>
              <div style={{ background: '#4d9e78' }}/>
              <div style={{ background: '#174D38' }}/>
              <div style={{ background: '#174D38' }}/>
              <div style={{ background: '#4d9e78' }}/>
            </div>
            <div>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 15, fontWeight: 600, color: '#111', letterSpacing: '0.01em' }}>
                TestSoftware
              </div>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 9, color: '#174D38', letterSpacing: '0.16em', textTransform: 'uppercase', marginTop: 2 }}>
                Admin Console
              </div>
            </div>
          </div>

          {/* Divider */}
          <div style={{ height: 1, background: '#f0f0f0', marginBottom: 32 }}/>

          {/* Heading */}
          <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 24, fontWeight: 400, color: '#111', letterSpacing: '-0.02em' }}>
              Sign in
            </div>
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#999', letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 6 }}>
              Administrator access only
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{
              padding: '10px 14px',
              background: '#fff5f5',
              border: '1px solid #fca5a5',
              fontSize: 12, color: '#dc2626',
              marginBottom: 20,
              fontFamily: "'IBM Plex Mono', monospace",
            }}>
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={submit}>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#888', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 7 }}>
                Email
              </div>
              <input
                type="email"
                placeholder="admin@company.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoFocus
                style={{
                  width: '100%', padding: '11px 13px',
                  background: '#fafafa',
                  border: '1.5px solid #e0e0e0',
                  color: '#111',
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: 13, outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
                onFocus={e => { e.target.style.borderColor = '#174D38'; e.target.style.background = '#fff' }}
                onBlur={e => { e.target.style.borderColor = '#e0e0e0'; e.target.style.background = '#fafafa' }}
              />
            </div>

            <div style={{ marginBottom: 28 }}>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#888', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 7 }}>
                Password
              </div>
              <input
                type="password"
                placeholder="••••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                style={{
                  width: '100%', padding: '11px 13px',
                  background: '#fafafa',
                  border: '1.5px solid #e0e0e0',
                  color: '#111',
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: 13, outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
                onFocus={e => { e.target.style.borderColor = '#174D38'; e.target.style.background = '#fff' }}
                onBlur={e => { e.target.style.borderColor = '#e0e0e0'; e.target.style.background = '#fafafa' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '13px',
                background: loading ? '#ccc' : '#174D38',
                border: 'none',
                color: loading ? '#999' : '#ffffff',
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 11, fontWeight: 600,
                letterSpacing: '0.16em', textTransform: 'uppercase',
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
              }}
              onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = '#1f6347' }}
              onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLElement).style.background = '#174D38' }}
            >
              {loading ? (
                <>
                  <div style={{ width: 10, height: 10, border: '1.5px solid #aaa', borderTopColor: '#555', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }}/>
                  Authenticating
                </>
              ) : 'Sign In →'}
            </button>
          </form>

          {/* Footer */}
          <div style={{ marginTop: 32, paddingTop: 20, borderTop: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e' }}/>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#bbb', letterSpacing: '0.06em' }}>
                System online
              </div>
            </div>
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: '#ccc' }}>
              v2.0
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}