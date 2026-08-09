const statusStyles = {
  HIGH: 'border-red-400/30 bg-red-500/10 text-red-50',
  CRITICAL: 'border-orange-300/30 bg-orange-500/10 text-orange-50'
}

function formatDistance(distance) {
  if (distance === null || distance === undefined || Number.isNaN(Number(distance))) return 'N/A'
  return `${Number(distance).toFixed(2)} km`
}

export default function EvacuationPanel({ evacuation = null, weather = null, risk = 'SAFE', onReplayGuidance }) {
  const normalizedRisk = String(risk || '').toUpperCase()
  if (normalizedRisk !== 'HIGH' && normalizedRisk !== 'CRITICAL') return null

  const shellClass = statusStyles[normalizedRisk] || statusStyles.HIGH
  const safeZone = evacuation?.safe_zone || {}
  const route = evacuation?.route || {}
  const weatherRain = Number(weather?.rainfall_mm ?? route?.rainfall_mm ?? 0)

  return (
    <section className={`rounded-3xl border p-4 backdrop-blur-xl ${shellClass}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.24em] text-white/70">Safe Route Evacuation</div>
          <div className="text-xl font-semibold">Evacuate only if the risk is HIGH or CRITICAL.</div>
          <div className="text-sm text-white/85">{evacuation?.summary || 'Move toward the nearest safer area and follow local evacuation guidance.'}</div>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <InfoPill label="Nearest safe zone" value={safeZone.name || evacuation?.temporary_shelter || 'Safer location'} />
            <InfoPill label="Direction" value={evacuation?.estimated_direction || 'north'} />
            <InfoPill label="Route distance" value={formatDistance(route.distance_km)} />
            <InfoPill label="Road access" value={evacuation?.road_accessibility_status || 'Unknown'} />
          </div>
        </div>

        <div className="grid min-w-[220px] gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-slate-100">
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-300">Temporary shelter</div>
            <div className="mt-1 font-semibold">{evacuation?.temporary_shelter || safeZone.name || 'Higher ground'}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-300">Safer elevation zone</div>
            <div className="mt-1 font-semibold">{evacuation?.safer_elevation_zone || 'Higher ground'}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-300">Rainfall context</div>
            <div className="mt-1 font-semibold">{weatherRain.toFixed(1)} mm</div>
          </div>
          <button
            type="button"
            onClick={onReplayGuidance}
            className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm font-semibold text-white transition hover:bg-white/15"
          >
            Replay guidance
          </button>
        </div>
      </div>
    </section>
  )
}

function InfoPill({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/15 px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.2em] text-white/65">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  )
}