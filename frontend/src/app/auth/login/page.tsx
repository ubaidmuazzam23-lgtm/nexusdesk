// Location: ./frontend/src/app/auth/login/page.tsx
'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({ email: '', password: '' })

  useEffect(() => {
    if (window.location.search.includes('registered=true')) {
      setSuccess('Account created! Sign in to continue.')
    }
    if (window.location.search.includes('reset=true')) {
      setSuccess('Password reset. Sign in with your new password.')
    }
    if (window.location.search.includes('activated=true')) {
      setSuccess('Account activated! Sign in to continue.')
    }
  }, [])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const d = await r.json()
      if (!r.ok) {
        if (d.detail === 'PENDING_ACTIVATION') {
          window.location.replace(`/auth/activate?email=${encodeURIComponent(form.email)}`)
          return
        }
        throw new Error(d.detail || 'Login failed')
      }
      localStorage.setItem('access_token', d.access_token)
      localStorage.setItem('refresh_token', d.refresh_token)
      localStorage.setItem('role', d.role)
      localStorage.setItem('full_name', d.full_name)
      localStorage.setItem('email', d.email)
      if (d.user_id) localStorage.setItem('user_id', d.user_id)
      if (d.role === 'admin') window.location.replace('/admin/overview')
      else if (d.role === 'engineer') window.location.replace('/engineer/dashboard')
      else if (d.role === 'manager') window.location.replace('/manager/overview')
      else window.location.replace('/chat')
    } catch (err: any) {
      setError(err.message)
      setLoading(false)
    }
  }

  const S = {
    page: { minHeight: '100vh', background: '#0a0a0a', display: 'grid', gridTemplateColumns: '1fr 1fr' } as React.CSSProperties,
    left: { background: '#0f0f0f', borderRight: '1px solid rgba(255,255,255,0.06)', padding: '56px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', position: 'relative', overflow: 'hidden' } as React.CSSProperties,
    right: { padding: '56px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' } as React.CSSProperties,
    inp: { width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', color: '#F2F2F2', fontSize: 14, outline: 'none', borderRadius: 2, fontFamily: 'inherit' } as React.CSSProperties,
    lbl: { fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(242,242,242,0.4)', marginBottom: 8, display: 'block', fontWeight: 500 } as React.CSSProperties,
  }

  return (
    <div style={S.page}>
      {/* Left */}
      <div style={S.left}>
        <div style={{ position: 'absolute', bottom: '10%', left: '-10%', width: 500, height: 500, background: 'radial-gradient(circle, rgba(23,77,56,0.18) 0%, transparent 65%)', pointerEvents: 'none' }}/>
        <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <svg width="32" height="32" viewBox="0 0 32 32">
            <polygon points="16,2 30,9 30,23 16,30 2,23 2,9" fill="#174D38"/>
            <circle cx="16" cy="16" r="4" fill="#4d9e78"/>
          </svg>
          <span style={{ fontFamily: 'Georgia, serif', fontSize: 22, fontWeight: 600, color: '#F2F2F2' }}>NexusDesk</span>
        </Link>
        <div>
          <h2 style={{ fontFamily: 'Georgia, serif', fontSize: 48, fontWeight: 500, lineHeight: 1.05, color: '#F2F2F2', marginBottom: 20 }}>
            Welcome<br/><span style={{ color: '#4d9e78' }}>back.</span>
          </h2>
          <p style={{ fontSize: 15, color: 'rgba(242,242,242,0.35)', lineHeight: 1.75, maxWidth: 340, marginBottom: 40 }}>
            Sign in to continue managing IT support at global scale.
          </p>
          {[
            { role: 'User',     color: '#174D38', desc: 'Chat with AI · Track tickets' },
            { role: 'Engineer', color: '#555',    desc: 'View queue · Resolve tickets' },
            { role: 'Manager',  color: '#5b3d8a', desc: 'Manage team · Assign tickets' },
            { role: 'Admin',    color: '#4D1717', desc: 'Manage platform · Full control' },
          ].map((r, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 4, marginBottom: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: r.color, flexShrink: 0 }}/>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#F2F2F2', marginBottom: 2 }}>{r.role}</div>
                <div style={{ fontSize: 11, color: 'rgba(242,242,242,0.3)' }}>{r.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: 'rgba(242,242,242,0.15)' }}>© 2026 NexusDesk</div>
      </div>

      {/* Right */}
      <div style={S.right}>
        <div style={{ width: '100%', maxWidth: 400 }}>
          <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 36, fontWeight: 500, color: '#F2F2F2', marginBottom: 8 }}>Sign in</h1>
          <p style={{ fontSize: 14, color: 'rgba(242,242,242,0.35)', marginBottom: 32 }}>Your role is detected automatically.</p>

          {success && (
            <div style={{ padding: '12px 16px', background: 'rgba(23,77,56,0.15)', border: '1px solid rgba(23,77,56,0.3)', color: '#4d9e78', fontSize: 13, marginBottom: 24, borderRadius: 2 }}>
              {success}
            </div>
          )}
          {error && (
            <div style={{ padding: '12px 16px', background: 'rgba(77,23,23,0.3)', border: '1px solid rgba(200,50,50,0.3)', color: '#f87171', fontSize: 13, marginBottom: 24, borderRadius: 2 }}>
              {error}
            </div>
          )}

          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <label style={S.lbl}>Email Address</label>
              <input style={S.inp} type="email" placeholder="you@company.com" value={form.email} onChange={set('email')}/>
            </div>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <label style={{ ...S.lbl, marginBottom: 0 }}>Password</label>
                <Link href="/auth/forgot-password" style={{ fontSize: 12, color: '#4d9e78', textDecoration: 'none' }}>Forgot password?</Link>
              </div>
              <input style={S.inp} type="password" placeholder="Your password" value={form.password} onChange={set('password')}/>
            </div>
            <button type="submit" disabled={loading} style={{ width: '100%', padding: '14px', background: loading ? '#0f3526' : '#174D38', color: '#F2F2F2', border: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', cursor: loading ? 'not-allowed' : 'pointer', borderRadius: 2, fontFamily: 'inherit', marginTop: 4 }}>
              {loading ? 'Signing in...' : 'Sign In →'}
            </button>
          </form>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16, margin: '28px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }}/>
            <span style={{ fontSize: 11, color: 'rgba(242,242,242,0.2)', letterSpacing: '0.08em' }}>OR</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.07)' }}/>
          </div>

          <Link href="/auth/activate" style={{ display: 'block', padding: '16px 18px', background: 'rgba(23,77,56,0.08)', border: '1px solid rgba(23,77,56,0.25)', borderRadius: 4, textDecoration: 'none', marginBottom: 24, transition: 'border 0.2s' }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(23,77,56,0.5)'}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor = 'rgba(23,77,56,0.25)'}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: '#4d9e78', marginBottom: 4 }}>Engineer? Activate your account →</div>
            <div style={{ fontSize: 12, color: 'rgba(242,242,242,0.35)' }}>First time? Use your email + temp password from the activation email.</div>
          </Link>

          <p style={{ fontSize: 13, color: 'rgba(242,242,242,0.3)', textAlign: 'center' }}>
            No account? <Link href="/auth/register" style={{ color: '#4d9e78', textDecoration: 'none' }}>Create one →</Link>
          </p>
        </div>
      </div>
    </div>
  )
}