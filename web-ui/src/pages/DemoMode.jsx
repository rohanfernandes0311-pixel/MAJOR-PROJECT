import { useMemo, useState } from 'react'
import MapView from '../shared/MapView'

const DEMO_LOCATIONS = [
  {
    id: 'wayanad',
    name: 'Kerala - Wayanad',
    label: 'RED ZONE',
    risk: 'CRITICAL',
    lat: 11.706,
    lng: 76.068,
    rainfall: 156,
    humidity: 96,
    wind: 17,
    temperature: 24,
    shelter: 'Kalpetta relief camp',
    elevation: 'Upper plateau corridor',
    accessibility: 'Roads under watch',
    direction: 'north-east',
    summary: 'Landslide-prone slopes with very high rainfall and saturation.',
    zones: [
      feature(11.706, 76.068, -0.12, 0.18, 0.14, 'Wayanad Ridge', 'CRITICAL'),
      feature(11.706, 76.068, 0.24, -0.06, 0.12, 'Wayanad Buffer', 'HIGH'),
      feature(11.706, 76.068, 0.56, 0.32, 0.10, 'Kalpetta Safe Point', 'LOW')
    ]
  },
  {
    id: 'kodagu',
    name: 'Karnataka - Kodagu / Madikeri',
    label: 'DANGER ZONE',
    risk: 'HIGH',
    lat: 12.424,
    lng: 75.738,
    rainfall: 104,
    humidity: 91,
    wind: 14,
    temperature: 23,
    shelter: 'Madikeri town safe shelter',
    elevation: 'Ridge-top evacuation path',
    accessibility: 'Partial access',
    direction: 'west',
    summary: 'Steep slopes and fast runoff can trigger sudden hillside failures.',
    zones: [
      feature(12.424, 75.738, -0.10, 0.12, 0.12, 'Kodagu Core', 'HIGH'),
      feature(12.424, 75.738, 0.18, -0.10, 0.09, 'Madikeri Safe Zone', 'LOW'),
      feature(12.424, 75.738, 0.42, 0.28, 0.08, 'Kodagu Ridge', 'MEDIUM')
    ]
  },
  {
    id: 'raigad',
    name: 'Maharashtra - Raigad',
    label: 'HIGH RISK',
    risk: 'HIGH',
    lat: 18.24,
    lng: 73.19,
    rainfall: 88,
    humidity: 84,
    wind: 12,
    temperature: 28,
    shelter: 'Alibag relief staging area',
    elevation: 'Safer coastal plateau',
    accessibility: 'Mostly open',
    direction: 'south-east',
    summary: 'Weather-driven instability near hill cuttings and transport corridors.',
    zones: [
      feature(18.24, 73.19, -0.08, 0.10, 0.11, 'Raigad Core', 'HIGH'),
      feature(18.24, 73.19, 0.16, -0.11, 0.09, 'Alibag Shelter', 'LOW'),
      feature(18.24, 73.19, 0.40, 0.24, 0.08, 'Raigad Watch', 'MEDIUM')
    ]
  }
]

function feature(centerLat, centerLng, latOffset, lngOffset, radius, name, riskLevel) {
  const lat = centerLat + latOffset
  const lng = centerLng + lngOffset
  return {
    type: 'Feature',
    properties: { name, risk_level: riskLevel },
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [lng - radius, lat - radius],
        [lng + radius, lat - radius],
        [lng + radius, lat + radius],
        [lng - radius, lat + radius],
        [lng - radius, lat - radius]
      ]]
    }
  }
}

function currentRoute(item) {
  const safeZone = item.zones.find((zone) => String(zone?.properties?.risk_level || '').toUpperCase() === 'LOW') || item.zones[0]
  const safeCoords = safeZone.geometry.coordinates[0]
  const safeCenter = safeCoords.reduce(
    (acc, pair) => ({ lat: acc.lat + pair[1], lng: acc.lng + pair[0] }),
    { lat: 0, lng: 0 }
  )
  const safeLat = safeCenter.lat / safeCoords.length
  const safeLng = safeCenter.lng / safeCoords.length
  return { start: [item.lat, item.lng], end: [safeLat, safeLng] }
}

export default function DemoMode() {
  const [activeId, setActiveId] = useState(DEMO_LOCATIONS[0].id)
  const active = useMemo(() => DEMO_LOCATIONS.find((item) => item.id === activeId) || DEMO_LOCATIONS[0], [activeId])

  const route = currentRoute(active)
  const zones = active.zones

  return (
    <div className="min-h-screen bg-[#061019] text-white">
      <div className="mx-auto max-w-screen-2xl p-4 md:p-6">
        <div className="mb-4 rounded-[2rem] border border-red-300/20 bg-gradient-to-r from-red-600/20 via-[#0b1726] to-[#061019] p-5 shadow-2xl">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.28em] text-red-200/80">Admin Demo Mode</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight">Disaster monitoring showcase</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-200/85">
                This sandboxed dashboard simulates red zones, live alerts, and evacuation visuals without touching live monitoring.
              </p>
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => window.location.assign('/admin')}
                className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white"
              >
                Back to Admin
              </button>
            </div>
          </div>
        </div>

        <section className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
          <div className="space-y-4">
            <div className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Launch Demo Mode</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {DEMO_LOCATIONS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveId(item.id)}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      item.id === activeId ? 'bg-red-500 text-white shadow-lg shadow-red-500/20' : 'bg-white/8 text-slate-100 hover:bg-white/12'
                    }`}
                  >
                    {item.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <MiniCard title="Location" value={active.name} accent={active.risk === 'CRITICAL' ? 'red' : 'orange'} />
              <MiniCard title="Status" value={active.label} accent={active.risk === 'CRITICAL' ? 'red' : 'orange'} />
              <MiniCard title="Rainfall" value={`${active.rainfall} mm`} accent="cyan" />
              <MiniCard title="Wind speed" value={`${active.wind} m/s`} accent="cyan" />
            </div>

            <div className="rounded-3xl border border-red-300/20 bg-red-500/10 p-4 backdrop-blur-xl">
              <div className="text-xs uppercase tracking-[0.24em] text-red-100/80">Risk simulation</div>
              <div className="mt-2 text-lg font-semibold">{active.summary}</div>
              <div className="mt-3 grid gap-2 text-sm text-red-50/90 sm:grid-cols-2">
                <ValueRow label="Temperature" value={`${active.temperature} °C`} />
                <ValueRow label="Humidity" value={`${active.humidity}%`} />
                <ValueRow label="Temporary shelter" value={active.shelter} />
                <ValueRow label="Safer direction" value={active.direction} />
                <ValueRow label="Elevation zone" value={active.elevation} />
                <ValueRow label="Access" value={active.accessibility} />
              </div>
            </div>
          </div>

          <div className="min-h-[68vh] overflow-hidden rounded-[2rem] border border-white/8 bg-[#08131e] shadow-2xl">
            <MapView zones={zones} userLocation={{ lat: active.lat, lng: active.lng }} route={route} risk={active.risk} />
          </div>
        </section>
      </div>
    </div>
  )
}

function MiniCard({ title, value, accent = 'orange' }) {
  const accentStyles = {
    red: 'border-red-400/20 bg-red-500/10 text-red-50',
    orange: 'border-orange-400/20 bg-orange-500/10 text-orange-50',
    cyan: 'border-cyan-400/20 bg-cyan-500/10 text-cyan-50'
  }
  return (
    <div className={`rounded-3xl border p-4 backdrop-blur-xl ${accentStyles[accent]}`}>
      <div className="text-[11px] uppercase tracking-[0.22em] text-white/65">{title}</div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
    </div>
  )
}

function ValueRow({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.2em] text-white/60">{label}</div>
      <div className="mt-1 font-semibold text-white">{value}</div>
    </div>
  )
}