'use client'
// File: frontend/src/app/admin/overview/page.tsx

import { useState, useEffect, useRef, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL

interface Overview {
  total: number; open: number; in_progress: number; resolved: number
  this_week: number; this_month: number; sla_compliance: number
  sla_breached: number; ai_resolution_rate: number
}
interface Engineer {
  id: string; engineer_id: string; full_name: string
  domain_expertise: string[]; region: string; timezone: string
  city: string; country: string; seniority_level: string
  max_ticket_capacity: number; active_ticket_count: number
  availability_status: string; is_active: boolean; is_activated: boolean
  total_resolved: number; sla_compliance_rate: number
}
interface Ticket {
  id: string; ticket_number: string; title: string; domain: string
  priority: string; status: string; engineer_name: string
  user_name: string; user_city: string; user_country: string
  user_timezone: string; created_at: string; sla_deadline: string; sla_breached: boolean
}

const CITY_COORDS: Record<string, [number, number]> = {
  'Dubai':[25.20,55.27],'Abu Dhabi':[24.45,54.38],
  'New York':[40.71,-74.01],'London':[51.51,-0.13],
  'Tokyo':[35.68,139.76],'Osaka':[34.69,135.50],
  'Mumbai':[19.07,72.87],'Bangalore':[12.97,77.59],
  'Bengaluru':[12.97,77.59],'Delhi':[28.61,77.21],
  'Chicago':[41.88,-87.63],'Paris':[48.85,2.35],
  'Nairobi':[-1.29,36.82],'Seattle':[47.61,-122.33],
  'Manchester':[53.48,-2.24],'Pune':[18.52,73.86],
  'Austin':[30.27,-97.74],'Stockholm':[59.33,18.07],
  'Hyderabad':[17.39,78.49],'Boston':[42.36,-71.06],
  'Dallas':[32.78,-96.80],'Denver':[39.74,-104.99],
  'Los Angeles':[34.05,-118.24],'San Francisco':[37.77,-122.42],
  'Atlanta':[33.75,-84.39],'Washington DC':[38.91,-77.04],
  'Miami':[25.77,-80.19],'Phoenix':[33.45,-112.07],
  'Toronto':[43.65,-79.38],'Vancouver':[49.28,-123.12],
  'Sydney':[-33.87,151.21],'Melbourne':[-37.81,144.96],
  'Seoul':[37.57,126.98],'Beijing':[39.91,116.39],
  'Shanghai':[31.23,121.47],'Shenzhen':[22.54,114.06],
  'Singapore':[1.35,103.82],'Riyadh':[24.69,46.72],
  'Cairo':[30.04,31.24],'Lagos':[6.45,3.40],
  'Accra':[5.60,-0.19],'Johannesburg':[-26.20,28.04],
  'Cape Town':[-33.92,18.42],'Casablanca':[33.59,-7.62],
  'Dakar':[14.69,-17.44],'Berlin':[52.52,13.40],
  'Munich':[48.14,11.58],'Frankfurt':[50.11,8.68],
  'Vienna':[48.21,16.37],'Warsaw':[52.23,21.01],
  'Prague':[50.08,14.44],'Lisbon':[38.72,-9.14],
  'Dublin':[53.33,-6.25],'Brussels':[50.85,4.35],
  'Bucharest':[44.43,26.10],'Copenhagen':[55.68,12.57],
  'Oslo':[59.91,10.75],'Helsinki':[60.17,24.94],
  'Gothenburg':[57.71,11.97],'Krakow':[50.06,19.94],
  'Bratislava':[48.15,17.11],'Lyon':[45.75,4.83],
  'Rome':[41.90,12.50],'Milan':[45.46,9.19],
  'Sao Paulo':[-23.55,-46.63],'São Paulo':[-23.55,-46.63],
  'Rio de Janeiro':[-22.91,-43.17],'Buenos Aires':[-34.60,-58.38],
  'Santiago':[-33.46,-70.65],'Bogota':[4.71,-74.07],
  'Lima':[-12.05,-77.04],'Mexico City':[19.43,-99.13],
  'Amman':[31.95,35.94],'Beirut':[33.89,35.50],
  'Doha':[25.28,51.53],'Karachi':[24.86,67.01],
  'Lahore':[31.55,74.35],'Islamabad':[33.72,73.06],
  'Dhaka':[23.81,90.41],'Kolkata':[22.57,88.36],
  'Chennai':[13.08,80.27],'Kochi':[9.93,76.26],
  'Kyoto':[35.01,135.77],'Nagoya':[35.18,136.90],
  'Busan':[35.18,129.08],'Abuja':[9.07,7.40],
  'Alexandria':[31.20,29.92],'Port Harcourt':[4.77,7.01],
  'Aarhus':[56.16,10.20],'Sapporo':[43.06,141.35],
  'Kumasi':[6.69,-1.62],'Enugu':[6.44,7.49],
}

const TZ_COORDS: Record<string, [number, number]> = {
  'Asia/Kolkata':[20.59,78.96],'Asia/Tokyo':[35.68,139.76],
  'Asia/Seoul':[37.57,126.98],'Asia/Singapore':[1.35,103.82],
  'Asia/Dubai':[25.20,55.27],'Asia/Shanghai':[31.23,121.47],
  'Asia/Riyadh':[24.69,46.72],'Asia/Karachi':[24.86,67.01],
  'Asia/Dhaka':[23.81,90.41],'Asia/Beirut':[33.89,35.50],
  'Asia/Amman':[31.95,35.94],'Asia/Qatar':[25.28,51.53],
  'Europe/London':[51.51,-0.13],'Europe/Paris':[48.85,2.35],
  'Europe/Berlin':[52.52,13.40],'Europe/Stockholm':[59.33,18.07],
  'Europe/Warsaw':[52.23,21.01],'Europe/Prague':[50.08,14.44],
  'Europe/Vienna':[48.21,16.37],'Europe/Oslo':[59.91,10.75],
  'Europe/Helsinki':[60.17,24.94],'Europe/Copenhagen':[55.68,12.57],
  'Europe/Dublin':[53.33,-6.25],'Europe/Brussels':[50.85,4.35],
  'Europe/Lisbon':[38.72,-9.14],'Europe/Bucharest':[44.43,26.10],
  'Europe/Bratislava':[48.15,17.11],'Europe/Rome':[41.90,12.50],
  'America/New_York':[40.71,-74.01],'America/Chicago':[41.88,-87.63],
  'America/Los_Angeles':[37.77,-122.42],'America/Denver':[39.74,-104.99],
  'America/Toronto':[43.65,-79.38],'America/Vancouver':[49.28,-123.12],
  'America/Sao_Paulo':[-23.55,-46.63],'America/Bogota':[4.71,-74.07],
  'America/Mexico_City':[19.43,-99.13],'America/Lima':[-12.05,-77.04],
  'America/Santiago':[-33.46,-70.65],
  'America/Argentina/Buenos_Aires':[-34.60,-58.38],
  'Australia/Sydney':[-33.87,151.21],'Africa/Nairobi':[-1.29,36.82],
  'Africa/Lagos':[6.45,3.40],'Africa/Accra':[5.60,-0.19],
  'Africa/Cairo':[30.04,31.24],'Africa/Johannesburg':[-26.20,28.04],
  'Africa/Casablanca':[33.59,-7.62],'Africa/Dakar':[14.69,-17.44],
  'America/Phoenix':[33.45,-112.07],
}

const getCoords = (city?: string, tz?: string): [number,number] | null => {
  if (city) {
    const c = CITY_COORDS[city]
    if (c) return c
    const key = Object.keys(CITY_COORDS).find(k => k.toLowerCase() === city.toLowerCase())
    if (key) return CITY_COORDS[key]
  }
  if (tz && TZ_COORDS[tz]) return TZ_COORDS[tz]
  return null
}

const haversine = (a: [number,number], b: [number,number]) => {
  const R = 6371
  const dLat = (b[0]-a[0]) * Math.PI/180
  const dLon = (b[1]-a[1]) * Math.PI/180
  const x = Math.sin(dLat/2)**2 + Math.cos(a[0]*Math.PI/180)*Math.cos(b[0]*Math.PI/180)*Math.sin(dLon/2)**2
  return Math.round(R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1-x)))
}

const dLabel = (d: string) => ({
  networking:'Networking',hardware:'Hardware',software:'Software',security:'Security',
  email_communication:'Email & Comm',identity_access:'Identity & Access',database:'Database',
  cloud:'Cloud',infrastructure:'Infrastructure',devops:'DevOps',
  erp_business_apps:'ERP & Business',endpoint_management:'Endpoint Mgmt',other:'Other',
}[d] || d)

const DOMAINS = ['networking','security','cloud','hardware','software','database','devops','infrastructure','identity_access','email_communication','erp_business_apps','endpoint_management']
const PRIORITIES = ['critical','high','medium','low']
const STATUSES = ['open','in_progress','resolved']

export default function OverviewPage() {
  const [overview, setOverview]   = useState<Overview | null>(null)
  const [engineers, setEngineers] = useState<Engineer[]>([])
  const [tickets, setTickets]     = useState<Ticket[]>([])
  const [loading, setLoading]     = useState(true)
  const [routeTkt, setRouteTkt]   = useState<Ticket | null>(null)
  const [mounted, setMounted]     = useState(false)
  const [mapLayer, setMapLayer]   = useState<'both'|'engineers'|'tickets'>('both')
  const [filterDomain, setFilterDomain]     = useState('')
  const [filterPriority, setFilterPriority] = useState('')
  const [filterStatus, setFilterStatus]     = useState('')
  const [filterEngAvail, setFilterEngAvail] = useState('')
  const [showLines, setShowLines] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())

  const mapRef     = useRef<HTMLDivElement>(null)
  const leafRef    = useRef<any>(null)
  const engMarkers = useRef<any[]>([])
  const tktMarkers = useRef<any[]>([])
  const lineGroup  = useRef<any>(null)   // L.layerGroup for lines
  const pulseLayer = useRef<any[]>([])
  // store line data so we can rebuild without re-fetching
  const lineData   = useRef<Array<{tCoords:[number,number], eCoords:[number,number], tkt:Ticket}>>([])

  const hdrs = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`
  }), [])

  const loadLeaflet = (): Promise<void> => new Promise((resolve) => {
    if ((window as any).L) { resolve(); return }
    if (!document.querySelector('#leaflet-css')) {
      const link = document.createElement('link')
      link.id = 'leaflet-css'; link.rel = 'stylesheet'
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
      document.head.appendChild(link)
    }
    const existing = document.querySelector('#leaflet-js')
    if (existing) { existing.addEventListener('load', () => resolve()); return }
    const s = document.createElement('script')
    s.id = 'leaflet-js'
    s.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
    s.onload = () => resolve()
    document.head.appendChild(s)
  })

  useEffect(() => { setMounted(true); fetchAll() }, [])

  useEffect(() => {
    if (mounted) loadLeaflet().then(() => buildMap())
  }, [mounted, engineers, tickets])

  // Layer visibility toggle
  useEffect(() => {
    const L = (window as any).L
    if (!L || !leafRef.current) return
    engMarkers.current.forEach(m => {
      try {
        if (mapLayer === 'tickets') leafRef.current.removeLayer(m)
        else leafRef.current.addLayer(m)
      } catch {}
    })
    tktMarkers.current.forEach(m => {
      try {
        if (mapLayer === 'engineers') leafRef.current.removeLayer(m)
        else leafRef.current.addLayer(m)
      } catch {}
    })
    pulseLayer.current.forEach(m => {
      try {
        if (mapLayer === 'engineers') leafRef.current.removeLayer(m)
        else leafRef.current.addLayer(m)
      } catch {}
    })
  }, [mapLayer])

  const fetchAll = async () => {
    setLoading(true)
    try {
      const [oR, eR, tR] = await Promise.all([
        fetch(`${API}/api/v1/analytics/overview`, { headers: hdrs() }),
        fetch(`${API}/api/v1/admin/engineers`, { headers: hdrs() }),
        fetch(`${API}/api/v1/admin/tickets?limit=100`, { headers: hdrs() }),
      ])
      if (oR.ok) setOverview(await oR.json())
      if (eR.ok) setEngineers(await eR.json())
      if (tR.ok) setTickets(await tR.json())
      setLastUpdated(new Date())
    } catch {}
    finally { setLoading(false) }
  }

  // ── Build lines helper — called from buildMap AND toggleLines ────────────
  const buildLineGroup = (L: any, ticketList: Ticket[], engineerList: Engineer[]) => {
    const group = L.layerGroup()
    lineData.current = []

    ticketList
      .filter(t => t.status !== 'resolved' && t.engineer_name)
      .forEach(tkt => {
        const tCoords = getCoords(tkt.user_city, tkt.user_timezone)
        if (!tCoords) return
        const eng = engineerList.find(e => e.full_name === tkt.engineer_name)
        if (!eng) return
        const eCoords = getCoords(eng.city, eng.timezone)
        if (!eCoords) return

        // Store for tooltip
        lineData.current.push({ tCoords, eCoords, tkt })

        const dist = haversine(tCoords, eCoords)
        const isCrit = tkt.priority === 'critical'

        const line = L.polyline([tCoords, eCoords], {
          color:     isCrit ? '#BE123C' : '#174D38',
          weight:    isCrit ? 3.5 : 2.5,
          opacity:   0.9,
          dashArray: isCrit ? '1 6' : '8 5',
        })

        line.bindTooltip(
          `<b>${tkt.ticket_number}</b> → ${tkt.engineer_name}<br/>${dist.toLocaleString()} km · ${tkt.priority}`,
          { direction: 'center', sticky: true }
        )
        group.addLayer(line)
      })

    return group
  }

  const buildMap = async () => {
    if (!mapRef.current) return
    const L = (window as any).L
    if (!L) return

    // Destroy old map
    if (leafRef.current) {
      leafRef.current.remove()
      leafRef.current = null
    }
    engMarkers.current = []
    tktMarkers.current = []
    pulseLayer.current = []
    lineGroup.current  = null

    // Pulse CSS
    if (!document.querySelector('#pulse-css')) {
      const style = document.createElement('style')
      style.id = 'pulse-css'
      style.textContent = `
        @keyframes pulse-ring {
          0%   { transform:translate(-50%,-50%) scale(1);   opacity:.9 }
          100% { transform:translate(-50%,-50%) scale(3.4); opacity:0  }
        }
        @keyframes pulse-ring2 {
          0%   { transform:translate(-50%,-50%) scale(1);   opacity:.7 }
          100% { transform:translate(-50%,-50%) scale(2.6); opacity:0  }
        }
        .pulse-ring {
          position:absolute; top:50%; left:50%;
          width:12px; height:12px; border-radius:50%;
          border:2.5px solid #BE123C;
          animation:pulse-ring 1.5s ease-out infinite;
        }
        .pulse-ring2 {
          position:absolute; top:50%; left:50%;
          width:12px; height:12px; border-radius:50%;
          border:2px solid #BE123C;
          animation:pulse-ring2 1.5s ease-out .6s infinite;
        }
        .eng-dot {
          width:13px; height:13px; border-radius:50%;
          border:2.5px solid #fff;
          box-shadow:0 1px 5px rgba(0,0,0,.35);
        }
        .leaflet-tooltip {
          font-family:"JetBrains Mono",monospace;
          font-size:11px; padding:4px 10px;
          border-radius:4px; border:1px solid #CBCBCB;
        }
      `
      document.head.appendChild(style)
    }

    const map = L.map(mapRef.current, {
      zoomControl: true, scrollWheelZoom: true, attributionControl: true,
    }).setView([20, 10], 2)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO', maxZoom: 19, subdomains: 'abcd',
    }).addTo(map)

    leafRef.current = map

    // ── Engineer markers ────────────────────────────────────────────────────
    engineers.filter(e => e.is_active && e.is_activated).forEach(eng => {
      const coords = getCoords(eng.city, eng.timezone)
      if (!coords) return

      const color = eng.availability_status === 'available'
        ? '#174D38' : eng.availability_status === 'busy' ? '#8a5a00' : '#6b6b6b'

      const icon = L.divIcon({
        html: `<div class="eng-dot" style="background:${color}"></div>`,
        className: '', iconSize: [13,13], iconAnchor: [6.5,6.5],
      })

      const m = L.marker(coords, { icon }).addTo(map)
      const domain = eng.domain_expertise?.[0] || 'unknown'
      m.bindPopup(`
        <div style="font-family:Inter,-apple-system,sans-serif;min-width:200px">
          <div style="font-weight:700;font-size:12px;margin-bottom:4px">${eng.full_name}</div>
          <div style="font-size:11px;color:#555;margin-bottom:1px">${eng.engineer_id} · ${eng.seniority_level || 'mid'}</div>
          <div style="font-size:11px;color:#555;margin-bottom:1px">${eng.timezone}</div>
          <div style="font-size:11px;color:#555;margin-bottom:6px">${eng.active_ticket_count}/${eng.max_ticket_capacity} tickets · ${eng.availability_status}</div>
          <span style="font-size:9px;padding:2px 8px;border-radius:10px;font-weight:600;text-transform:uppercase;background:${color}22;color:${color};border:1px solid ${color}55">${eng.availability_status}</span>
          <span style="font-size:9px;padding:2px 8px;border-radius:10px;font-weight:600;background:#f0f4f8;color:#555;margin-left:4px">${dLabel(domain)}</span>
        </div>
      `, { maxWidth: 240 })

      engMarkers.current.push(m)
    })

    // ── Ticket markers + pulse ──────────────────────────────────────────────
    const cityGroups: Record<string, Ticket[]> = {}
    tickets.forEach(t => {
      const key = t.user_city || t.user_timezone || 'unknown'
      if (!cityGroups[key]) cityGroups[key] = []
      cityGroups[key].push(t)
    })

    Object.entries(cityGroups).forEach(([, cityTickets]) => {
      const first = cityTickets[0]
      const baseCoords = getCoords(first.user_city, first.user_timezone)
      if (!baseCoords) return

      const openCount  = cityTickets.filter(t => t.status !== 'resolved').length
      const critCount  = cityTickets.filter(t => t.priority === 'critical' && t.status !== 'resolved').length
      const total      = cityTickets.length
      const isCritical = critCount > 0

      const coords: [number,number] = [
        baseCoords[0] + (Math.random()-0.5)*0.3,
        baseCoords[1] + (Math.random()-0.5)*0.3,
      ]

      const color = isCritical ? '#BE123C' : openCount > 0 ? '#D97706' : '#64748B'
      const size  = Math.min(10 + total * 1.5, 20)

      // Pulse rings for critical
      if (isCritical) {
        const pulseIcon = L.divIcon({
          html: `<div style="position:relative;width:${size}px;height:${size}px">
            <div class="pulse-ring"></div>
            <div class="pulse-ring2"></div>
          </div>`,
          className: '', iconSize: [size,size], iconAnchor: [size/2,size/2],
        })
        const pm = L.marker(coords, { icon: pulseIcon, zIndexOffset: 0 }).addTo(map)
        pulseLayer.current.push(pm)
      }

      const tIcon = L.divIcon({
        html: `<div style="
          width:${size}px;height:${size}px;border-radius:3px;
          background:${color};border:2px solid #fff;
          box-shadow:0 2px 8px rgba(0,0,0,.32);
          display:grid;place-items:center;
          font-size:${total>1?8:0}px;font-weight:700;color:#fff;
          font-family:monospace;
        ">${total>1?total:''}</div>`,
        className: '', iconSize: [size,size], iconAnchor: [size/2,size/2],
      })

      const m = L.marker(coords, { icon: tIcon, zIndexOffset: 100 }).addTo(map)

      const rows = cityTickets.slice(0,5).map(t => `
        <div style="display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #f0f0f0">
          <span style="font-family:monospace;font-size:10px;font-weight:600;color:#174D38;min-width:56px">${t.ticket_number}</span>
          <span style="font-size:10px;color:#555;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.title}</span>
          <span style="font-size:9px;padding:1px 5px;border-radius:3px;font-weight:600;text-transform:uppercase;
            background:${t.priority==='critical'?'#fef2f2':t.priority==='high'?'#fffbeb':'#f0fdf4'};
            color:${t.priority==='critical'?'#BE123C':t.priority==='high'?'#D97706':'#16a34a'}">
            ${t.priority}
          </span>
        </div>
      `).join('')

      m.bindPopup(`
        <div style="font-family:Inter,-apple-system,sans-serif;min-width:270px">
          <div style="font-weight:700;font-size:12px;margin-bottom:5px">
            📍 ${first.user_city||'Unknown'}${first.user_country?', '+first.user_country:''}
          </div>
          <div style="display:flex;gap:6px;margin-bottom:8px">
            <span style="font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;background:#f0fdf4;color:#16a34a">${total} ticket${total!==1?'s':''}</span>
            ${openCount>0?`<span style="font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;background:#fffbeb;color:#D97706">${openCount} open</span>`:''}
            ${critCount>0?`<span style="font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;background:#fef2f2;color:#BE123C">${critCount} critical</span>`:''}
          </div>
          ${rows}
          ${cityTickets.length>5?`<div style="font-size:10px;color:#999;margin-top:4px">+${cityTickets.length-5} more</div>`:''}
        </div>
      `, { maxWidth: 310 })

      tktMarkers.current.push(m)
    })

    // ── Build line group (not added to map yet) ─────────────────────────────
    lineGroup.current = buildLineGroup(L, tickets, engineers)
    console.log(`Lines built: ${lineData.current.length} connections`)
  }

  // ── Toggle routing lines ────────────────────────────────────────────────
  const toggleLines = () => {
    const L = (window as any).L
    if (!L || !leafRef.current) return

    if (!showLines) {
      // Show lines — rebuild fresh each time to be safe
      if (lineGroup.current) {
        try { leafRef.current.removeLayer(lineGroup.current) } catch {}
      }
      lineGroup.current = buildLineGroup(L, tickets, engineers)
      lineGroup.current.addTo(leafRef.current)
      setShowLines(true)
    } else {
      // Hide lines
      if (lineGroup.current) {
        try { leafRef.current.removeLayer(lineGroup.current) } catch {}
      }
      setShowLines(false)
    }
  }

  const filteredTickets = tickets.filter(t => {
    if (filterDomain && t.domain !== filterDomain) return false
    if (filterPriority && t.priority !== filterPriority) return false
    if (filterStatus && t.status !== filterStatus) return false
    return true
  })

  const filteredEngineers = engineers.filter(e => {
    if (filterEngAvail && e.availability_status !== filterEngAvail) return false
    return true
  })

  const avail  = engineers.filter(e => e.availability_status === 'available' && e.is_active).length
  const busy   = engineers.filter(e => e.availability_status === 'busy' && e.is_active).length
  const away   = engineers.filter(e => e.availability_status === 'away' && e.is_active).length
  const atRisk = filteredTickets.filter(t => t.sla_breached || (t.sla_deadline && new Date(t.sla_deadline) < new Date(Date.now() + 20*60*1000)))
  const bars   = [3,2,4,5,8,12,18,22,26,31,28,24,19,22,27,33,29,25,21,17,14,11,9,6]
  const maxB   = Math.max(...bars)

  if (!mounted) return null

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        .ovw{font-family:"Inter",-apple-system,sans-serif;font-size:13px;color:#141414;background:#F2F2F2;min-height:100%}
        .ovw *{box-sizing:border-box}
        .ovw .card{background:#fff;border:1px solid #CBCBCB;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
        .ovw .c-head{padding:10px 14px;border-bottom:1px solid #CBCBCB;display:flex;align-items:center;gap:8px;min-height:40px;flex-wrap:wrap}
        .ovw .c-head h3{margin:0;font-size:12px;font-weight:600;letter-spacing:-.01em}
        .ovw .c-sub{font-size:11px;color:#6b6b6b;font-family:"JetBrains Mono",monospace}
        .ovw .stat-lbl{font-size:10px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.08em;font-family:"JetBrains Mono",monospace;font-weight:600}
        .ovw .stat-v{font-size:24px;font-weight:700;letter-spacing:-.02em;line-height:1.1;margin-top:5px;font-feature-settings:"tnum";font-family:"JetBrains Mono",monospace}
        .ovw .stat-d{font-size:11px;color:#6b6b6b;font-family:"JetBrains Mono",monospace;margin-top:3px}
        .ovw .stat-d.up{color:#1a7a4a}.ovw .stat-d.dn{color:#4D1717}
        .ovw .pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:10px;font-size:10px;font-weight:600;font-family:"JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.04em;background:#EBEBEB;color:#3a3a3a;border:1px solid #CBCBCB;white-space:nowrap}
        .ovw .pill-ok{background:#e6f4ed;color:#1a7a4a;border-color:transparent}
        .ovw .pill-warn{background:#fdf4e3;color:#8a5a00;border-color:transparent}
        .ovw .pill-crit{background:#f5eaea;color:#4D1717;border-color:transparent}
        .ovw .pill-grn{background:#e8f2ed;color:#174D38;border-color:transparent}
        .ovw .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#a0a0a0;flex-shrink:0}
        .ovw .dot-ok{background:#1a7a4a}.ovw .dot-warn{background:#8a5a00}.ovw .dot-crit{background:#4D1717}
        .ovw .pulse{animation:ovw-pulse 1.8s ease-in-out infinite}
        @keyframes ovw-pulse{0%,100%{opacity:1}50%{opacity:.3}}
        .ovw table.dt{width:100%;border-collapse:collapse;font-size:12px}
        .ovw table.dt th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#6b6b6b;padding:8px 12px;background:#EBEBEB;border-bottom:1px solid #CBCBCB;font-weight:600;font-family:"JetBrains Mono",monospace;white-space:nowrap}
        .ovw table.dt td{padding:8px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
        .ovw table.dt tr:hover td{background:#f9f9f9;cursor:pointer}
        .ovw .bar{height:6px;background:#EBEBEB;border-radius:3px;overflow:hidden;border:1px solid #CBCBCB}
        .ovw .bar-f{height:100%;transition:width .4s;border-radius:3px}
        .ovw .sp{font-family:"JetBrains Mono",monospace;font-size:11px;font-weight:600;padding:2px 8px;border-radius:3px;background:#EBEBEB;min-width:40px;text-align:center;border:1px solid #CBCBCB;display:inline-block}
        .ovw .sp-top{background:#174D38;color:#fff;border-color:#174D38}
        .ovw .mono{font-family:"JetBrains Mono",monospace}
        .ovw .muted{color:#6b6b6b}.ovw .small{font-size:11px}.ovw .tiny{font-size:10px}
        .ovw .trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .ovw .row{display:flex;align-items:center;gap:8px}
        .ovw .grow{flex:1}
        .ovw .btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;color:#141414;font-family:inherit;font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background .1s}
        .ovw .btn:hover{background:#EBEBEB}
        .ovw .btn-p{background:#174D38!important;color:#fff!important;border-color:#174D38!important}
        .ovw .btn-sm{height:24px;padding:0 8px;font-size:11px}
        .ovw .btn-on{background:#141414!important;color:#fff!important;border-color:#141414!important}
        .ovw select.flt{height:26px;padding:0 8px;border-radius:4px;border:1px solid #CBCBCB;background:#fff;font-family:"JetBrains Mono",monospace;font-size:10px;color:#141414;cursor:pointer;text-transform:uppercase;letter-spacing:.04em}
        .ovw select.flt:focus{outline:none;border-color:#174D38}
        .leaflet-container{background:#e8ede9!important;font-family:"Inter",sans-serif!important}
        .leaflet-popup-content-wrapper{border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.12);border:1px solid #CBCBCB}
        .leaflet-popup-content{font-family:"Inter",sans-serif;font-size:12px;margin:10px 14px}
        .leaflet-control-attribution{font-size:9px!important}
      `}</style>

      <div className="ovw" style={{ padding:16, display:'flex', flexDirection:'column', gap:14 }}>

        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', gap:12 }}>
          <div>
            <div style={{ fontSize:16, fontWeight:700, letterSpacing:'-.02em' }}>Overview</div>
            <div style={{ fontSize:11, color:'#6b6b6b', fontFamily:'"JetBrains Mono",monospace', marginTop:1 }}>
              Last updated {lastUpdated.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
            </div>
          </div>
          <div style={{ flex:1 }}/>
          <select className="flt" value={filterDomain} onChange={e => setFilterDomain(e.target.value)}>
            <option value="">All Domains</option>
            {DOMAINS.map(d => <option key={d} value={d}>{dLabel(d)}</option>)}
          </select>
          <select className="flt" value={filterPriority} onChange={e => setFilterPriority(e.target.value)}>
            <option value="">All Priorities</option>
            {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="flt" value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace('_',' ')}</option>)}
          </select>
          <select className="flt" value={filterEngAvail} onChange={e => setFilterEngAvail(e.target.value)}>
            <option value="">All Engineers</option>
            <option value="available">Available</option>
            <option value="busy">Busy</option>
            <option value="away">Away</option>
          </select>
          {(filterDomain||filterPriority||filterStatus||filterEngAvail) && (
            <button className="btn btn-sm" onClick={() => { setFilterDomain(''); setFilterPriority(''); setFilterStatus(''); setFilterEngAvail('') }}>✕ Clear</button>
          )}
          <button className="btn btn-sm btn-p" onClick={fetchAll} disabled={loading}>
            {loading ? '…' : '↻ Refresh'}
          </button>
        </div>

        {/* KPIs */}
        {overview && (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:10 }}>
            {[
              { l:'AI Resolution',    v:`${overview.ai_resolution_rate}%`, d:'of resolved tickets', du:'up' },
              { l:'Open Tickets',     v:filteredTickets.filter(t=>t.status!=='resolved').length, d:`${filteredTickets.filter(t=>t.status==='in_progress').length} in progress`, du:'' },
              { l:'SLA Compliance',   v:`${overview.sla_compliance}%`, d:`${overview.sla_breached>0?'▼ '+overview.sla_breached+' breached':'▲ all in SLA'}`, du:overview.sla_compliance>=90?'up':'dn' },
              { l:'Mapped Tickets',   v:tickets.filter(t=>getCoords(t.user_city,t.user_timezone)!==null).length, d:'with known location', du:'' },
              { l:'Engineers Active', v:`${avail+busy}/${engineers.filter(e=>e.is_active).length}`,
                d:<span className="row" style={{gap:6}}>
                  <span className="dot dot-ok"/>{avail} avail
                  <span className="dot dot-warn"/>{busy} busy
                  <span className="dot dot-crit"/>{away} away
                </span>, du:'' },
            ].map((s,i) => (
              <div key={i} className="card" style={{ padding:'14px 16px' }}>
                <div className="stat-lbl">{s.l}</div>
                <div className="stat-v">{s.v}</div>
                <div className={`stat-d ${s.du}`}>{s.d as any}</div>
              </div>
            ))}
          </div>
        )}

        {/* Map + Activity */}
        <div style={{ display:'grid', gridTemplateColumns:'1.5fr 1fr', gap:12 }}>
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
              <h3>Global Load — Engineers & Tickets</h3>
              <span className="grow"/>
              <span className="dot dot-ok pulse"/>
              <span className="c-sub" style={{marginLeft:4}}>LIVE</span>
            </div>

            {/* Map controls */}
            <div style={{ padding:'8px 14px', display:'flex', gap:6, alignItems:'center', borderBottom:'1px solid #f0f0f0', flexWrap:'wrap' }}>
              <span className="tiny muted" style={{fontFamily:'"JetBrains Mono",monospace',textTransform:'uppercase',letterSpacing:'.04em',marginRight:2}}>Layers</span>
              {(['both','engineers','tickets'] as const).map(l => (
                <button key={l} className={`btn btn-sm ${mapLayer===l?'btn-on':''}`} onClick={() => setMapLayer(l)}>
                  {l==='both'?'All':l==='engineers'?'● Engineers':'■ Tickets'}
                </button>
              ))}
              <div style={{ width:1, height:18, background:'#CBCBCB', margin:'0 2px' }}/>
              <button
                className={`btn btn-sm ${showLines?'btn-on':''}`}
                onClick={toggleLines}
                style={showLines ? { background:'#174D38', color:'#fff', borderColor:'#174D38' } : {}}
              >
                {showLines ? '✕ Hide Routes' : '── Show Routes'}
              </button>
              <span className="grow"/>
              <span className="tiny muted mono">{engMarkers.current.length} eng · {tktMarkers.current.length} loc</span>
            </div>

            <div style={{ padding:12 }}>
              <div ref={mapRef} style={{ height:300, borderRadius:4, overflow:'hidden', background:'#e8ede9' }}/>
              <div style={{ marginTop:8, display:'flex', gap:10, flexWrap:'wrap' }}>
                <span className="tiny muted mono" style={{textTransform:'uppercase',letterSpacing:'.04em'}}>Eng:</span>
                {[{c:'#174D38',l:'Available'},{c:'#8a5a00',l:'Busy'},{c:'#6b6b6b',l:'Away'}].map(x=>(
                  <span key={x.l} style={{fontSize:10,fontFamily:'"JetBrains Mono",monospace',color:'#6b6b6b',textTransform:'uppercase',letterSpacing:'.04em',display:'flex',alignItems:'center',gap:4}}>
                    <span style={{width:8,height:8,borderRadius:'50%',background:x.c,display:'inline-block'}}/>
                    {x.l}
                  </span>
                ))}
                <span style={{width:1,background:'#CBCBCB',height:12,alignSelf:'center'}}/>
                <span className="tiny muted mono" style={{textTransform:'uppercase',letterSpacing:'.04em'}}>Tickets:</span>
                {[{c:'#BE123C',l:'Critical'},{c:'#D97706',l:'Open'},{c:'#64748B',l:'Resolved'}].map(x=>(
                  <span key={x.l} style={{fontSize:10,fontFamily:'"JetBrains Mono",monospace',color:'#6b6b6b',textTransform:'uppercase',letterSpacing:'.04em',display:'flex',alignItems:'center',gap:4}}>
                    <span style={{width:7,height:7,borderRadius:2,background:x.c,display:'inline-block'}}/>
                    {x.l}
                  </span>
                ))}
                {showLines && (
                  <span style={{fontSize:10,fontFamily:'"JetBrains Mono",monospace',color:'#174D38',display:'flex',alignItems:'center',gap:4}}>
                    <span style={{width:16,height:2,borderTop:'2px dashed #174D38',display:'inline-block'}}/>
                    Route (hover = distance)
                  </span>
                )}
              </div>
            </div>

            {/* Region bars */}
            <div style={{ padding:'8px 14px 12px', display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, borderTop:'1px solid #CBCBCB' }}>
              {[
                { n:'APAC', tzPrefixes:['Asia/','Australia/'] },
                { n:'EMEA', tzPrefixes:['Europe/','Africa/'] },
                { n:'AMER', tzPrefixes:['America/'] },
              ].map(r => {
                const rEngs = engineers.filter(e => r.tzPrefixes.some(p => e.timezone?.startsWith(p)))
                const active = rEngs.filter(e => e.availability_status !== 'away').length
                const total  = rEngs.length || 1
                const pct    = active / total
                return (
                  <div key={r.n}>
                    <div className="row" style={{marginBottom:5}}>
                      <span className="small" style={{fontWeight:600}}>{r.n}</span>
                      <span className="grow"/>
                      <span className="tiny mono muted">{active}/{rEngs.length} eng</span>
                    </div>
                    <div className="bar">
                      <div className="bar-f" style={{width:`${pct*100}%`,background:pct>.85?'#4D1717':pct>.5?'#8a5a00':'#174D38'}}/>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Live activity */}
          <div className="card" style={{display:'flex',flexDirection:'column'}}>
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              <h3>Live Activity</h3>
              <span className="grow"/>
              <span className="c-sub">stream</span>
            </div>
            <div style={{flex:1,overflowY:'auto',maxHeight:360}}>
              {filteredTickets.slice(0,15).map((t,i) => (
                <div key={i} style={{padding:'8px 14px',borderBottom:'1px solid #f0f0f0',display:'grid',gridTemplateColumns:'84px 1fr auto',gap:8,alignItems:'center'}}>
                  <span className="tiny muted mono">{new Date(t.created_at).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})}</span>
                  <div style={{fontSize:12,overflow:'hidden'}}>
                    <div className="trunc"><b>{t.status==='resolved'?'Resolved':'Opened'}</b> · <span className="mono" style={{color:'#174D38'}}>{t.ticket_number}</span></div>
                    <div className="tiny muted">{t.user_name} · {t.user_city||dLabel(t.domain)}</div>
                  </div>
                  <span className={`pill ${t.priority==='critical'?'pill-crit':t.priority==='high'?'pill-warn':'pill-grn'}`}>{t.priority}</span>
                </div>
              ))}
              {filteredTickets.length===0 && (
                <div style={{padding:32,textAlign:'center',color:'#6b6b6b',fontSize:12}}>No activity matching filters</div>
              )}
            </div>
          </div>
        </div>

        {/* At Risk + Volume */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#4D1717" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              <h3>SLA At Risk</h3>
              <span className="grow"/>
              {atRisk.length>0 && <span className="pill pill-crit">{atRisk.length} ACTIVE</span>}
            </div>
            <table className="dt">
              <thead><tr><th>ID</th><th>Issue</th><th>Location</th><th>Engineer</th><th>Priority</th></tr></thead>
              <tbody>
                {atRisk.length===0 ? (
                  <tr><td colSpan={5} style={{textAlign:'center',padding:24,color:'#6b6b6b'}}>
                    <span className="dot dot-ok" style={{marginRight:6}}/>All tickets within SLA
                  </td></tr>
                ) : atRisk.slice(0,6).map(t => (
                  <tr key={t.id} onClick={() => setRouteTkt(t)}>
                    <td className="mono" style={{color:'#174D38',fontWeight:600}}>{t.ticket_number}</td>
                    <td style={{maxWidth:140}}><div className="trunc">{t.title}</div></td>
                    <td className="small muted">{t.user_city||'—'}</td>
                    <td className="small muted">{t.engineer_name||'—'}</td>
                    <td><span className={`pill ${t.priority==='critical'?'pill-crit':t.priority==='high'?'pill-warn':'pill-grn'}`}>{t.priority}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="c-head">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><rect x="18" y="3" width="4" height="18"/><rect x="10" y="8" width="4" height="13"/><rect x="2" y="13" width="4" height="8"/></svg>
              <h3>Ticket Volume · last 24h</h3>
            </div>
            <div style={{padding:16}}>
              <div style={{display:'flex',alignItems:'flex-end',gap:3,height:110}}>
                {bars.map((b,i) => (
                  <div key={i} style={{flex:1,height:`${(b/maxB)*100}%`,background:i>15?'#174D38':'#CBCBCB',borderRadius:'2px 2px 0 0',minHeight:2}}/>
                ))}
              </div>
              <div className="row" style={{marginTop:8}}>
                <span className="tiny muted mono">00:00</span>
                <span className="grow"/>
                <span className="tiny muted mono">NOW</span>
              </div>
              {overview && (
                <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8,marginTop:14,paddingTop:12,borderTop:'1px solid #f0f0f0'}}>
                  {[
                    {l:'This Week',v:overview.this_week},
                    {l:'This Month',v:overview.this_month},
                    {l:'Total',v:overview.total},
                  ].map((s,i) => (
                    <div key={i} style={{textAlign:'center'}}>
                      <div className="stat-lbl">{s.l}</div>
                      <div style={{fontSize:20,fontWeight:700,fontFamily:'"JetBrains Mono",monospace',letterSpacing:'-.02em',marginTop:3}}>{s.v}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Engineer table */}
        <div className="card">
          <div className="c-head">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#174D38" strokeWidth="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
            <h3>Engineers</h3>
            <span className="grow"/>
            <select className="flt" value={filterEngAvail} onChange={e => setFilterEngAvail(e.target.value)}>
              <option value="">All Availability</option>
              <option value="available">Available</option>
              <option value="busy">Busy</option>
              <option value="away">Away</option>
            </select>
            <span className="c-sub">{filteredEngineers.length} engineers</span>
          </div>
          <div style={{overflowX:'auto'}}>
            <table className="dt">
              <thead><tr><th>Engineer</th><th>Domain</th><th>Location</th><th>Timezone</th><th>Status</th><th>Load</th><th>Resolved</th></tr></thead>
              <tbody>
                {filteredEngineers.slice(0,10).map((e,i) => (
                  <tr key={e.id}>
                    <td>
                      <div style={{display:'flex',alignItems:'center',gap:8}}>
                        <div style={{width:22,height:22,borderRadius:3,background:'#174D38',color:'#fff',display:'grid',placeItems:'center',fontSize:9,fontWeight:700,flexShrink:0}}>
                          {e.full_name.charAt(0)}
                        </div>
                        <div>
                          <div style={{fontWeight:500}}>{e.full_name}</div>
                          <div className="tiny muted mono">{e.engineer_id}</div>
                        </div>
                      </div>
                    </td>
                    <td>{e.domain_expertise.map(d => dLabel(d)).join(', ')}</td>
                    <td className="small">{e.city}{e.country?', '+e.country:''}</td>
                    <td className="tiny muted mono">{e.timezone}</td>
                    <td>
                      <span className="row" style={{gap:5}}>
                        <span className={`dot ${e.availability_status==='available'?'dot-ok':e.availability_status==='busy'?'dot-warn':'dot-crit'}`}/>
                        <span className="small">{e.availability_status}</span>
                      </span>
                    </td>
                    <td>
                      <div style={{display:'flex',alignItems:'center',gap:6}}>
                        <div style={{width:48,height:4,background:'#EBEBEB',borderRadius:2,overflow:'hidden'}}>
                          <div style={{height:'100%',width:`${(e.active_ticket_count/e.max_ticket_capacity)*100}%`,background:e.active_ticket_count/e.max_ticket_capacity>.8?'#4D1717':e.active_ticket_count/e.max_ticket_capacity>.5?'#8a5a00':'#174D38',borderRadius:2}}/>
                        </div>
                        <span className="tiny mono muted">{e.active_ticket_count}/{e.max_ticket_capacity}</span>
                      </div>
                    </td>
                    <td className="mono small">{e.total_resolved||'—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Routing Modal */}
      {routeTkt && (
        <div style={{position:'fixed',inset:0,background:'rgba(20,20,20,.4)',zIndex:100,display:'grid',placeItems:'center',backdropFilter:'blur(2px)'}} onClick={() => setRouteTkt(null)}>
          <div className="ovw card" onClick={e => e.stopPropagation()} style={{width:820,maxHeight:'80vh',overflow:'hidden',display:'flex',flexDirection:'column',boxShadow:'0 12px 32px rgba(0,0,0,.14)'}}>
            <div className="c-head" style={{background:'#174D38',borderRadius:'6px 6px 0 0',borderBottom:'none'}}>
              <h3 style={{color:'#fff'}}>Routing Decision</h3>
              <span style={{fontFamily:'"JetBrains Mono",monospace',fontSize:11,color:'rgba(255,255,255,.6)',marginLeft:4}}>· {routeTkt.ticket_number}</span>
              <span className="grow"/>
              <button className="btn btn-sm" style={{background:'transparent',borderColor:'rgba(255,255,255,.3)',color:'rgba(255,255,255,.7)'}} onClick={() => setRouteTkt(null)}>✕</button>
            </div>
            <div style={{padding:'10px 14px',borderBottom:'1px solid #CBCBCB',background:'#EBEBEB',display:'flex',alignItems:'center',gap:8,fontSize:12}}>
              <span className="mono muted">{routeTkt.ticket_number}</span>
              <span style={{fontWeight:500}}>{routeTkt.title}</span>
              <span className="grow"/>
              {routeTkt.user_city && <span className="tiny muted">📍 {routeTkt.user_city}{routeTkt.user_country?', '+routeTkt.user_country:''}</span>}
              <span className={`pill ${routeTkt.priority==='critical'?'pill-crit':routeTkt.priority==='high'?'pill-warn':'pill-grn'}`}>{routeTkt.priority}</span>
            </div>
            <div style={{overflow:'auto',flex:1}}>
              <table className="dt">
                <thead><tr><th>#</th><th>Engineer</th><th>Location</th><th>Status</th><th>Domain</th><th>Load</th><th>Distance</th><th>Score</th></tr></thead>
                <tbody>
                  {engineers
                    .filter(e => e.is_active && e.is_activated)
                    .map(e => {
                      const dm  = e.domain_expertise.includes(routeTkt.domain) ? 40 : 8
                      const av  = e.availability_status==='available'?20:e.availability_status==='busy'?8:0
                      const wl  = Math.round(Math.max(0,15-(e.active_ticket_count/e.max_ticket_capacity)*15))
                      const tot = dm+av+wl+8
                      const tCoords = getCoords(routeTkt.user_city, routeTkt.user_timezone)
                      const eCoords = getCoords(e.city, e.timezone)
                      const dist = tCoords && eCoords ? haversine(tCoords, eCoords) : null
                      return { e, dm, av, wl, tot, dist, excl: e.availability_status==='away' }
                    })
                    .sort((a,b) => b.tot-a.tot)
                    .map((s,i) => (
                      <tr key={s.e.id} style={s.excl?{opacity:.38}:{}}>
                        <td className="mono muted">{i+1}</td>
                        <td>
                          <div style={{display:'flex',alignItems:'center',gap:8}}>
                            <div style={{width:20,height:20,borderRadius:3,background:'#174D38',color:'#fff',display:'grid',placeItems:'center',fontSize:9,fontWeight:700,flexShrink:0}}>
                              {s.e.full_name.charAt(0)}
                            </div>
                            <div>
                              <div style={{fontWeight:500}}>{s.e.full_name}</div>
                              <div className="tiny muted">{s.e.domain_expertise.map(d=>dLabel(d)).join(', ')}</div>
                            </div>
                          </div>
                        </td>
                        <td className="small">{s.e.city}<div className="tiny muted">{s.e.timezone}</div></td>
                        <td>
                          <span className="row" style={{gap:5,fontSize:12}}>
                            <span className={`dot ${s.e.availability_status==='available'?'dot-ok':s.e.availability_status==='busy'?'dot-warn':'dot-crit'}`}/>
                            {s.e.availability_status}
                          </span>
                        </td>
                        <td className="mono small">{s.dm}</td>
                        <td>
                          <div style={{display:'flex',alignItems:'center',gap:6}}>
                            <div style={{width:36,height:4,background:'#EBEBEB',borderRadius:2,overflow:'hidden'}}>
                              <div style={{height:'100%',width:`${(s.e.active_ticket_count/s.e.max_ticket_capacity)*100}%`,background:'#8a5a00',borderRadius:2}}/>
                            </div>
                            <span className="tiny mono muted">{s.e.active_ticket_count}/{s.e.max_ticket_capacity}</span>
                          </div>
                        </td>
                        <td className="mono small">
                          {s.dist !== null ? (
                            <span style={{color:s.dist<1000?'#1a7a4a':s.dist<5000?'#8a5a00':'#4D1717'}}>
                              {s.dist.toLocaleString()} km
                            </span>
                          ) : '—'}
                        </td>
                        <td><span className={`sp ${i===0&&!s.excl?'sp-top':''}`}>{s.excl?'×':s.tot}</span></td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <div style={{padding:'10px 14px',borderTop:'1px solid #CBCBCB',display:'flex',alignItems:'center',gap:8}}>
              <span className="small muted mono">Domain 40 · Availability 20 · Load 15 · TZ 8</span>
              <span className="grow"/>
              <button className="btn btn-sm" onClick={() => setRouteTkt(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}