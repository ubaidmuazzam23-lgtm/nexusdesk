'use client'
// File: frontend/src/app/auth/register/page.tsx

import { useState, useEffect } from 'react'
import Link from 'next/link'

// Country → cities → timezone mapping
const COUNTRY_DATA: Record<string, { cities: { name: string; timezone: string }[] }> = {
  'India':           { cities: [{ name: 'Mumbai',         timezone: 'Asia/Kolkata' }, { name: 'Delhi', timezone: 'Asia/Kolkata' }, { name: 'Bangalore', timezone: 'Asia/Kolkata' }, { name: 'Chennai', timezone: 'Asia/Kolkata' }, { name: 'Hyderabad', timezone: 'Asia/Kolkata' }, { name: 'Pune', timezone: 'Asia/Kolkata' }] },
  'United States':   { cities: [{ name: 'New York',       timezone: 'America/New_York' }, { name: 'Chicago', timezone: 'America/Chicago' }, { name: 'Denver', timezone: 'America/Denver' }, { name: 'Los Angeles', timezone: 'America/Los_Angeles' }, { name: 'Phoenix', timezone: 'America/Phoenix' }, { name: 'Anchorage', timezone: 'America/Anchorage' }] },
  'United Kingdom':  { cities: [{ name: 'London',         timezone: 'Europe/London' }, { name: 'Manchester', timezone: 'Europe/London' }, { name: 'Edinburgh', timezone: 'Europe/London' }] },
  'Australia':       { cities: [{ name: 'Sydney',         timezone: 'Australia/Sydney' }, { name: 'Melbourne', timezone: 'Australia/Melbourne' }, { name: 'Brisbane', timezone: 'Australia/Brisbane' }, { name: 'Perth', timezone: 'Australia/Perth' }, { name: 'Adelaide', timezone: 'Australia/Adelaide' }, { name: 'Darwin', timezone: 'Australia/Darwin' }] },
  'Canada':          { cities: [{ name: 'Toronto',        timezone: 'America/Toronto' }, { name: 'Vancouver', timezone: 'America/Vancouver' }, { name: 'Calgary', timezone: 'America/Edmonton' }, { name: 'Montreal', timezone: 'America/Toronto' }] },
  'Germany':         { cities: [{ name: 'Berlin',         timezone: 'Europe/Berlin' }, { name: 'Munich', timezone: 'Europe/Berlin' }, { name: 'Hamburg', timezone: 'Europe/Berlin' }] },
  'France':          { cities: [{ name: 'Paris',          timezone: 'Europe/Paris' }, { name: 'Lyon', timezone: 'Europe/Paris' }, { name: 'Marseille', timezone: 'Europe/Paris' }] },
  'Japan':           { cities: [{ name: 'Tokyo',          timezone: 'Asia/Tokyo' }, { name: 'Osaka', timezone: 'Asia/Tokyo' }, { name: 'Fukuoka', timezone: 'Asia/Tokyo' }] },
  'China':           { cities: [{ name: 'Shanghai',       timezone: 'Asia/Shanghai' }, { name: 'Beijing', timezone: 'Asia/Shanghai' }, { name: 'Shenzhen', timezone: 'Asia/Shanghai' }] },
  'Singapore':       { cities: [{ name: 'Singapore',      timezone: 'Asia/Singapore' }] },
  'UAE':             { cities: [{ name: 'Dubai',          timezone: 'Asia/Dubai' }, { name: 'Abu Dhabi', timezone: 'Asia/Dubai' }] },
  'Saudi Arabia':    { cities: [{ name: 'Riyadh',         timezone: 'Asia/Riyadh' }, { name: 'Jeddah', timezone: 'Asia/Riyadh' }] },
  'Brazil':          { cities: [{ name: 'São Paulo',      timezone: 'America/Sao_Paulo' }, { name: 'Rio de Janeiro', timezone: 'America/Sao_Paulo' }, { name: 'Brasília', timezone: 'America/Sao_Paulo' }, { name: 'Manaus', timezone: 'America/Manaus' }] },
  'Netherlands':     { cities: [{ name: 'Amsterdam',      timezone: 'Europe/Amsterdam' }, { name: 'Rotterdam', timezone: 'Europe/Amsterdam' }] },
  'South Africa':    { cities: [{ name: 'Johannesburg',   timezone: 'Africa/Johannesburg' }, { name: 'Cape Town', timezone: 'Africa/Johannesburg' }] },
  'Nigeria':         { cities: [{ name: 'Lagos',          timezone: 'Africa/Lagos' }, { name: 'Abuja', timezone: 'Africa/Lagos' }] },
  'Kenya':           { cities: [{ name: 'Nairobi',        timezone: 'Africa/Nairobi' }] },
  'Pakistan':        { cities: [{ name: 'Karachi',        timezone: 'Asia/Karachi' }, { name: 'Lahore', timezone: 'Asia/Karachi' }, { name: 'Islamabad', timezone: 'Asia/Karachi' }] },
  'Bangladesh':      { cities: [{ name: 'Dhaka',          timezone: 'Asia/Dhaka' }, { name: 'Chittagong', timezone: 'Asia/Dhaka' }] },
  'Indonesia':       { cities: [{ name: 'Jakarta',        timezone: 'Asia/Jakarta' }, { name: 'Surabaya', timezone: 'Asia/Jakarta' }, { name: 'Makassar', timezone: 'Asia/Makassar' }, { name: 'Jayapura', timezone: 'Asia/Jayapura' }] },
  'Malaysia':        { cities: [{ name: 'Kuala Lumpur',   timezone: 'Asia/Kuala_Lumpur' }, { name: 'Penang', timezone: 'Asia/Kuala_Lumpur' }] },
  'Philippines':     { cities: [{ name: 'Manila',         timezone: 'Asia/Manila' }, { name: 'Cebu', timezone: 'Asia/Manila' }] },
  'South Korea':     { cities: [{ name: 'Seoul',          timezone: 'Asia/Seoul' }, { name: 'Busan', timezone: 'Asia/Seoul' }] },
  'Mexico':          { cities: [{ name: 'Mexico City',    timezone: 'America/Mexico_City' }, { name: 'Guadalajara', timezone: 'America/Mexico_City' }, { name: 'Tijuana', timezone: 'America/Tijuana' }] },
  'Argentina':       { cities: [{ name: 'Buenos Aires',   timezone: 'America/Argentina/Buenos_Aires' }, { name: 'Córdoba', timezone: 'America/Argentina/Cordoba' }] },
  'Italy':           { cities: [{ name: 'Rome',           timezone: 'Europe/Rome' }, { name: 'Milan', timezone: 'Europe/Rome' }] },
  'Spain':           { cities: [{ name: 'Madrid',         timezone: 'Europe/Madrid' }, { name: 'Barcelona', timezone: 'Europe/Madrid' }] },
  'Russia':          { cities: [{ name: 'Moscow',         timezone: 'Europe/Moscow' }, { name: 'Saint Petersburg', timezone: 'Europe/Moscow' }, { name: 'Novosibirsk', timezone: 'Asia/Novosibirsk' }, { name: 'Vladivostok', timezone: 'Asia/Vladivostok' }] },
  'Turkey':          { cities: [{ name: 'Istanbul',       timezone: 'Europe/Istanbul' }, { name: 'Ankara', timezone: 'Europe/Istanbul' }] },
  'Egypt':           { cities: [{ name: 'Cairo',          timezone: 'Africa/Cairo' }, { name: 'Alexandria', timezone: 'Africa/Cairo' }] },
  'Sweden':          { cities: [{ name: 'Stockholm',      timezone: 'Europe/Stockholm' }, { name: 'Gothenburg', timezone: 'Europe/Stockholm' }] },
  'Norway':          { cities: [{ name: 'Oslo',            timezone: 'Europe/Oslo' }] },
  'Denmark':         { cities: [{ name: 'Copenhagen',      timezone: 'Europe/Copenhagen' }, { name: 'Aarhus', timezone: 'Europe/Copenhagen' }] },
  'Finland':         { cities: [{ name: 'Helsinki',        timezone: 'Europe/Helsinki' }] },
  'Poland':          { cities: [{ name: 'Warsaw',          timezone: 'Europe/Warsaw' }, { name: 'Krakow', timezone: 'Europe/Warsaw' }] },
  'Czech Republic':  { cities: [{ name: 'Prague',          timezone: 'Europe/Prague' }] },
  'Austria':         { cities: [{ name: 'Vienna',          timezone: 'Europe/Vienna' }] },
  'Belgium':         { cities: [{ name: 'Brussels',        timezone: 'Europe/Brussels' }] },
  'Romania':         { cities: [{ name: 'Bucharest',       timezone: 'Europe/Bucharest' }] },
  'Slovakia':        { cities: [{ name: 'Bratislava',      timezone: 'Europe/Bratislava' }] },
  'Portugal':        { cities: [{ name: 'Lisbon',          timezone: 'Europe/Lisbon' }] },
  'Ireland':         { cities: [{ name: 'Dublin',          timezone: 'Europe/Dublin' }] },
  'Colombia':        { cities: [{ name: 'Bogota',          timezone: 'America/Bogota' }] },
  'Chile':           { cities: [{ name: 'Santiago',        timezone: 'America/Santiago' }] },
  'Peru':            { cities: [{ name: 'Lima',            timezone: 'America/Lima' }] },
  'Ghana':           { cities: [{ name: 'Accra',           timezone: 'Africa/Accra' }, { name: 'Kumasi', timezone: 'Africa/Accra' }] },
  'Morocco':         { cities: [{ name: 'Casablanca',      timezone: 'Africa/Casablanca' }] },
  'Senegal':         { cities: [{ name: 'Dakar',           timezone: 'Africa/Dakar' }] },
  'Lebanon':         { cities: [{ name: 'Beirut',          timezone: 'Asia/Beirut' }] },
  'Jordan':          { cities: [{ name: 'Amman',           timezone: 'Asia/Amman' }] },
  'Qatar':           { cities: [{ name: 'Doha',            timezone: 'Asia/Qatar' }] },
  'Other':           { cities: [{ name: 'Other',           timezone: 'UTC' }] },
}

const COUNTRIES = Object.keys(COUNTRY_DATA).sort((a, b) => a === 'Other' ? 1 : b === 'Other' ? -1 : a.localeCompare(b))

const checks = (password: string) => [
  { rule: 'At least 8 characters',    pass: password.length >= 8 },
  { rule: 'One uppercase letter',      pass: /[A-Z]/.test(password) },
  { rule: 'One number',                pass: /[0-9]/.test(password) },
]

export default function RegisterPage() {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mounted, setMounted] = useState(false)
  const [form, setForm] = useState({
    full_name: '', email: '', password: '', confirm: '',
    country: '', city: '', timezone: '',
  })

  useEffect(() => { setMounted(true) }, [])

  const countryData  = COUNTRY_DATA[form.country]
  const cities       = countryData?.cities || []
  const multiCity    = cities.length > 1

  const handleCountryChange = (country: string) => {
    const data = COUNTRY_DATA[country]
    if (!data) return
    // Auto-select first city if only one
    const firstCity = data.cities[0]
    setForm(f => ({
      ...f,
      country,
      city:     data.cities.length === 1 ? firstCity.name : '',
      timezone: data.cities.length === 1 ? firstCity.timezone : '',
    }))
  }

  const handleCityChange = (cityName: string) => {
    const city = cities.find(c => c.name === cityName)
    setForm(f => ({ ...f, city: cityName, timezone: city?.timezone || '' }))
  }

  const step1Valid = form.full_name.trim().length >= 2 && form.email.includes('@') &&
    checks(form.password).every(c => c.pass) && form.password === form.confirm

  const step2Valid = form.country !== '' && form.city !== '' && form.timezone !== ''

  const submit = async () => {
    if (!step2Valid) return
    setLoading(true)
    setError('')
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: form.full_name,
          email:     form.email,
          password:  form.password,
          country:   form.country,
          city:      form.city,
          timezone:  form.timezone,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Registration failed')
      window.location.replace('/auth/login?registered=true')
    } catch (err: any) {
      setError(err.message)
      setLoading(false)
    }
  }

  if (!mounted) return null

  const S = {
    page: { minHeight: '100vh', background: '#0a0a0a', display: 'grid', gridTemplateColumns: '1fr 1fr', fontFamily: 'DM Sans, sans-serif' } as React.CSSProperties,
    left: { background: '#0f0f0f', borderRight: '1px solid rgba(255,255,255,0.06)', padding: '56px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', position: 'relative', overflow: 'hidden' } as React.CSSProperties,
    right: { padding: '56px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center' } as React.CSSProperties,
    inp: { width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', color: '#F2F2F2', fontSize: 14, outline: 'none', borderRadius: 2, fontFamily: 'inherit' } as React.CSSProperties,
    sel: { width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', color: '#F2F2F2', fontSize: 14, outline: 'none', borderRadius: 2, fontFamily: 'inherit', appearance: 'none' as const, cursor: 'pointer' } as React.CSSProperties,
    lbl: { fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(242,242,242,0.4)', marginBottom: 8, display: 'block', fontWeight: 500 } as React.CSSProperties,
    muted: { color: 'rgba(242,242,242,0.35)' } as React.CSSProperties,
  }

  return (
    <div style={S.page}>
      {/* Left */}
      <div style={S.left}>
        <div style={{ position: 'absolute', bottom: '10%', left: '-10%', width: 500, height: 500, background: 'radial-gradient(circle, rgba(23,77,56,0.18) 0%, transparent 65%)', pointerEvents: 'none' }}/>
        <Link href="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <svg width="32" height="32" viewBox="0 0 32 32"><polygon points="16,2 30,9 30,23 16,30 2,23 2,9" fill="#174D38"/><circle cx="16" cy="16" r="4" fill="#4d9e78"/></svg>
          <span style={{ fontFamily: 'Georgia, serif', fontSize: 22, fontWeight: 600, color: '#F2F2F2' }}>NexusDesk</span>
        </Link>
        <div>
          <h2 style={{ fontFamily: 'Georgia, serif', fontSize: 44, fontWeight: 500, lineHeight: 1.05, color: '#F2F2F2', marginBottom: 20 }}>
            Get started<br/><span style={{ color: '#4d9e78' }}>today.</span>
          </h2>
          <p style={{ fontSize: 15, color: 'rgba(242,242,242,0.35)', lineHeight: 1.75, maxWidth: 340, marginBottom: 40 }}>
            AI-powered IT support that resolves issues intelligently and routes tickets to the right engineer globally.
          </p>
          {/* Steps */}
          {[
            { n: '01', label: 'Account Details',  active: step === 1 },
            { n: '02', label: 'Your Location',    active: step === 2 },
          ].map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: s.active ? '#174D38' : 'rgba(255,255,255,0.05)', border: `1px solid ${s.active ? '#174D38' : 'rgba(255,255,255,0.1)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: s.active ? '#F2F2F2' : 'rgba(242,242,242,0.3)', flexShrink: 0 }}>{s.n}</div>
              <span style={{ fontSize: 13, color: s.active ? '#F2F2F2' : 'rgba(242,242,242,0.3)', fontWeight: s.active ? 600 : 400 }}>{s.label}</span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 12, color: 'rgba(242,242,242,0.15)' }}>© 2026 NexusDesk</div>
      </div>

      {/* Right */}
      <div style={S.right}>
        <div style={{ width: '100%', maxWidth: 420 }}>

          {error && (
            <div style={{ padding: '12px 16px', background: 'rgba(77,23,23,0.3)', border: '1px solid rgba(200,50,50,0.3)', color: '#f87171', fontSize: 13, marginBottom: 24, borderRadius: 2 }}>{error}</div>
          )}

          {/* ── Step 1 ── */}
          {step === 1 && (
            <>
              <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 36, fontWeight: 500, color: '#F2F2F2', marginBottom: 8 }}>Create account</h1>
              <p style={{ fontSize: 14, ...S.muted, marginBottom: 32 }}>Step 1 of 2 — Account details</p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div>
                  <label style={S.lbl}>Full Name</label>
                  <input style={S.inp} type="text" placeholder="Ubaid Kundlik" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}/>
                </div>
                <div>
                  <label style={S.lbl}>Email Address</label>
                  <input style={S.inp} type="email" placeholder="you@company.com" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}/>
                </div>
                <div>
                  <label style={S.lbl}>Password</label>
                  <input style={S.inp} type="password" placeholder="Min 8 chars, 1 uppercase, 1 number" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}/>
                  {form.password && (
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {checks(form.password).map((c, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 14, height: 14, borderRadius: '50%', background: c.pass ? 'rgba(23,77,56,0.3)' : 'rgba(255,255,255,0.05)', border: `1px solid ${c.pass ? '#4d9e78' : 'rgba(255,255,255,0.1)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 8, color: c.pass ? '#4d9e78' : 'transparent' }}>✓</div>
                          <span style={{ fontSize: 12, color: c.pass ? '#4d9e78' : 'rgba(242,242,242,0.3)' }}>{c.rule}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <label style={S.lbl}>Confirm Password</label>
                  <input style={S.inp} type="password" placeholder="Repeat password" value={form.confirm} onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}/>
                  {form.confirm && form.password !== form.confirm && (
                    <div style={{ marginTop: 6, fontSize: 12, color: '#f87171' }}>Passwords do not match</div>
                  )}
                </div>
                <button onClick={() => { setError(''); setStep(2) }} disabled={!step1Valid} style={{ width: '100%', padding: '14px', background: step1Valid ? '#174D38' : '#0f3526', color: step1Valid ? '#F2F2F2' : 'rgba(242,242,242,0.3)', border: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', cursor: step1Valid ? 'pointer' : 'not-allowed', borderRadius: 2, fontFamily: 'inherit' }}>
                  Continue →
                </button>
              </div>
            </>
          )}

          {/* ── Step 2 ── */}
          {step === 2 && (
            <>
              <h1 style={{ fontFamily: 'Georgia, serif', fontSize: 36, fontWeight: 500, color: '#F2F2F2', marginBottom: 8 }}>Your location</h1>
              <p style={{ fontSize: 14, ...S.muted, marginBottom: 32 }}>Step 2 of 2 — Used for smart ticket routing</p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

                {/* Country */}
                <div>
                  <label style={S.lbl}>Country</label>
                  <select style={S.sel} value={form.country} onChange={e => handleCountryChange(e.target.value)}>
                    <option value="" disabled>Select your country</option>
                    {COUNTRIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>

                {/* City — shows only after country selected */}
                {form.country && (
                  <div>
                    <label style={S.lbl}>City</label>
                    {multiCity ? (
                      <select style={S.sel} value={form.city} onChange={e => handleCityChange(e.target.value)}>
                        <option value="" disabled>Select your city</option>
                        {cities.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                      </select>
                    ) : (
                      <input style={{ ...S.inp, color: 'rgba(242,242,242,0.5)', cursor: 'default' }} value={form.city} readOnly/>
                    )}
                  </div>
                )}

                {/* Timezone — auto-filled, read-only */}
                {form.timezone && (
                  <div>
                    <label style={S.lbl}>Timezone (auto-detected)</label>
                    <div style={{ position: 'relative' }}>
                      <input style={{ ...S.inp, color: '#4d9e78', cursor: 'default', paddingRight: 40 }} value={form.timezone} readOnly/>
                      <span style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: '#4d9e78' }}>✓</span>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(242,242,242,0.3)' }}>
                      Your local time: {(() => { try { return new Date().toLocaleTimeString('en-US', { timeZone: form.timezone, hour: '2-digit', minute: '2-digit', hour12: true }) } catch { return '' } })()}
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 12 }}>
                  <button onClick={() => setStep(1)} style={{ flex: 1, padding: '14px', background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(242,242,242,0.4)', fontSize: 14, cursor: 'pointer', borderRadius: 2, fontFamily: 'inherit' }}>← Back</button>
                  <button onClick={submit} disabled={!step2Valid || loading} style={{ flex: 2, padding: '14px', background: step2Valid && !loading ? '#174D38' : '#0f3526', color: step2Valid && !loading ? '#F2F2F2' : 'rgba(242,242,242,0.3)', border: 'none', fontSize: 14, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', cursor: step2Valid && !loading ? 'pointer' : 'not-allowed', borderRadius: 2, fontFamily: 'inherit' }}>
                    {loading ? 'Creating...' : 'Create Account →'}
                  </button>
                </div>
              </div>
            </>
          )}

          <p style={{ marginTop: 32, fontSize: 13, color: 'rgba(242,242,242,0.3)', textAlign: 'center' }}>
            Already have an account?{' '}
            <Link href="/auth/login" style={{ color: '#4d9e78', textDecoration: 'none' }}>Sign in →</Link>
          </p>
        </div>
      </div>
    </div>
  )
}