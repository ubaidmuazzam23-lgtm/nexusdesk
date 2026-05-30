// Location: ./frontend/src/app/auth/activate/page.tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function ActivatePage() {
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    email: '', temp_password: '', new_password: '', confirm: ''
  })

  const checks = [
    { rule: 'At least 8 characters', pass: form.new_password.length >= 8 },
    { rule: 'One uppercase letter',  pass: /[A-Z]/.test(form.new_password) },
    { rule: 'One number',            pass: /[0-9]/.test(form.new_password) },
  ]

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (form.new_password !== form.confirm) { setError('Passwords do not match'); return }
    if (!checks.every(c => c.pass)) { setError('Password does not meet requirements'); return }
    setLoading(true)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/activate-engineer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email,
          temp_password: form.temp_password,
          new_password: form.new_password,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Activation failed')
      setDone(true)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const S = {
    page: { minHeight: '100vh', background: '#0a0a0a', display: 'grid', gridTemplateColumns: '1fr 1fr', fontFamily: 'DM Sans, sans-serif' } as React.CSSProperties,
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
          <h2 style={{ fontFamily: 'Georgia, serif', fontSize: 44, fontWeight: 500, lineHeight: 1.05, color: '#F2F2F2', marginBottom: 20 }}>
            Activate your<br/><span style={{ color: '#4d9e78' }}>account.</span>
          </h2>
          <p style={{ fontSize: 15, color: 'rgba(242,242,242,0.4)', lineHeight: 1.75, maxWidth: 360, marginBottom: 36 }}>
            This is a one-time process. Use the credentials from your email to set your permanent password.
          </p>
          {[
            { n: '01', t: 'Check your email',        d: 'Find the activation email with your temp password.' },
            { n: '02', t: 'Enter your credentials',  d: 'Use your email and temp password to verify your identity.' },
            { n: '03', t: 'Set new password',         d: 'Choose a strong permanent password.' },
          ].map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
              <div style={{ fontFamily: 'Georgia, serif', fontSize: 13, color: '#174D38', fontWeight: 600, flexShrink: 0, marginTop: 2 }}>{s.n}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#F2F2F2', marginBottom: 4 }}>{s.t}</div>
                <div style={{ fontSize: 12, color: 'rgba(242,242,242,0.35)', lineHeight: 1.6 }}>{s.d}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: 'rgba(242,242,242,0.15)' }}>© 2026 NexusDesk</div>
      </div>

      {/* Right */}
      <div style={S.right}>
        <div style={{ width: '100%', maxWidth: 420 }}>
          {done ? (
            <div style={{ textAlign: 'center' }}>
              <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'rgba(23,77,56,0.2)', border: '2px solid #174D38', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px', fontSize: 28, color: '#4d9e78' }}>✓</div>
              <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 30, fontWeight: 500, color: '#F2F2F2', marginBottom: 12 }}>Account Activated!</h1>
              <p style={{ fontSize: 14, color: 'rgba(242,242,242,0.4)', marginBottom: 32, lineHeight: 1.6 }}>
                Your account is now active. Sign in to get started.
              </p>
              <Link href="/auth/login" style={{ display: 'inline-block', padding: '14px 40px', background: '#174D38', color: '#F2F2F2', textDecoration: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderRadius: 2 }}>
                Sign In →
              </Link>
            </div>
          ) : (
            <>
              <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 32, fontWeight: 500, color: '#F2F2F2', marginBottom: 8 }}>Activate Account</h1>
              <p style={{ fontSize: 14, color: 'rgba(242,242,242,0.35)', marginBottom: 32 }}>
                Works for both engineer and manager accounts.
              </p>

              {error && (
                <div style={{ padding: '12px 16px', background: 'rgba(77,23,23,0.3)', border: '1px solid rgba(200,50,50,0.3)', color: '#f87171', fontSize: 13, marginBottom: 24, borderRadius: 2 }}>
                  {error}
                </div>
              )}

              <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div>
                  <label style={S.lbl}>Your Email</label>
                  <input
                    style={S.inp} type="email"
                    placeholder="your@email.com"
                    value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    required
                  />
                </div>
                <div>
                  <label style={S.lbl}>Temporary Password (from email)</label>
                  <input
                    style={S.inp} type="password"
                    placeholder="Paste from your email"
                    value={form.temp_password}
                    onChange={e => setForm(f => ({ ...f, temp_password: e.target.value }))}
                    required
                  />
                </div>

                <div style={{ height: 1, background: 'rgba(255,255,255,0.07)', margin: '4px 0' }}/>

                <div>
                  <label style={S.lbl}>New Password</label>
                  <input
                    style={S.inp} type="password"
                    placeholder="Min 8 chars, 1 uppercase, 1 number"
                    value={form.new_password}
                    onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))}
                  />
                  {form.new_password && (
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {checks.map((c, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 14, height: 14, borderRadius: '50%', background: c.pass ? 'rgba(23,77,56,0.3)' : 'rgba(255,255,255,0.05)', border: `1px solid ${c.pass ? '#4d9e78' : 'rgba(255,255,255,0.1)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 8, color: c.pass ? '#4d9e78' : 'transparent' }}>✓</div>
                          <span style={{ fontSize: 12, color: c.pass ? '#4d9e78' : 'rgba(242,242,242,0.3)' }}>{c.rule}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <label style={S.lbl}>Confirm New Password</label>
                  <input
                    style={S.inp} type="password"
                    placeholder="Repeat new password"
                    value={form.confirm}
                    onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  style={{ width: '100%', padding: '14px', background: loading ? '#0f3526' : '#174D38', color: '#F2F2F2', border: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', cursor: loading ? 'not-allowed' : 'pointer', borderRadius: 2, fontFamily: 'inherit', marginTop: 4 }}
                >
                  {loading ? 'Activating...' : 'Activate My Account →'}
                </button>
              </form>

              <p style={{ marginTop: 28, fontSize: 13, color: 'rgba(242,242,242,0.3)', textAlign: 'center' }}>
                Already activated?{' '}
                <Link href="/auth/login" style={{ color: '#4d9e78', textDecoration: 'none' }}>Sign in →</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}