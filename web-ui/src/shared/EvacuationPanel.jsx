const statusStyles = {
  HIGH: 'border-orange-300/35 bg-orange-500/10 text-orange-50',
  CRITICAL: 'border-rose-300/40 bg-rose-500/15 text-rose-50'
}

export default function EvacuationPanel({ risk = 'SAFE', destination = '', route = null, loading = false, error = '', onDestinationChange, onFindRoute, onReplayGuidance }) {
  const normalizedRisk = String(risk || '').toUpperCase().replace(' RISK', '')
  if (normalizedRisk !== 'HIGH' && normalizedRisk !== 'CRITICAL') return null

  const critical = normalizedRisk === 'CRITICAL'
  return (
    <section aria-labelledby="safe-route-title" className={`rounded-md border p-4 ${statusStyles[normalizedRisk]}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.24em]">SAFE ROUTE GUIDANCE</div>
          <h2 id="safe-route-title" className="mt-1 text-xl font-black">{critical ? 'CRITICAL LANDSLIDE RISK' : 'HIGH LANDSLIDE RISK'}</h2>
          <p className="mt-2 text-sm text-white/90">{critical ? 'You are currently inside a critical-risk zone. Move away from the affected area and follow official emergency guidance.' : 'You are inside a high-risk zone. Avoid the affected area and prepare to move if local authorities advise it.'}</p>
        </div>
        <button type="button" onClick={onReplayGuidance} className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-sm font-semibold">Play safety guidance</button>
      </div>

      <div className="mt-4 rounded-md border border-white/10 bg-black/20 p-4">
        <label htmlFor="safe-route-destination" className="text-sm font-semibold">Destination coordinates</label>
        <p className="mt-1 text-xs text-white/65">Enter latitude and longitude separated by a comma. LandSense will request a route that reduces exposure to configured risk zones.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            id="safe-route-destination"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={destination}
            onChange={(event) => onDestinationChange(event.target.value)}
            placeholder="Example: 11.6200, 76.0900"
            aria-describedby={error ? 'safe-route-error' : 'safe-route-disclaimer'}
            className="min-w-0 flex-1 rounded-xl border border-white/15 bg-[#091521] px-3 py-2 text-white placeholder:text-slate-500"
          />
          <button type="button" onClick={onFindRoute} disabled={loading || !destination.trim()} className={`rounded-xl px-4 py-2.5 text-sm font-bold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50 ${critical ? 'bg-rose-200' : 'bg-orange-200'}`}>{loading ? 'Finding safer route...' : 'Find Safer Route'}</button>
        </div>
        {error ? <p id="safe-route-error" role="alert" className="mt-3 text-sm font-semibold text-rose-100">{error}</p> : null}
        {route ? <div role="status" className="mt-3 rounded-xl border border-cyan-200/25 bg-cyan-400/10 p-3 text-sm text-cyan-50"><p className="font-bold">Recommended safer route displayed on the map.</p><p className="mt-1">{route.distanceKm == null ? 'Distance estimate unavailable.' : `Approximate route distance: ${route.distanceKm.toFixed(2)} km.`}</p></div> : null}
        <p id="safe-route-disclaimer" className="mt-3 text-xs text-white/65">A safer route is guidance, not a guarantee of safety. Conditions can change; follow official instructions and visible road closures.</p>
      </div>
    </section>
  )
}
