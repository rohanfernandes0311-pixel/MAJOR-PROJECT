import React from 'react'

export default function PrecipitationCard({ observation, loading = false }) {
  const time = value => new Date(value).toLocaleString('en-IN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata',
  })
  return (
    <div aria-busy={loading}>
      <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Recent precipitation</div>
      {loading ? <p role="status" className="mt-2 text-sm">Loading satellite data…</p>
        : !observation ? <p role="status" className="mt-2 text-sm">Live data unavailable.</p>
          : <>
            <div className="mt-2 text-xl font-semibold">{observation.precipitation_rate.toFixed(2)} mm/h</div>
            <div className="text-xs text-slate-600">Precipitation rate · 30-minute mean</div>
            <p className="mt-1 text-xs text-slate-500">Latest available satellite observation</p>
            <p className="mt-2 text-xs text-slate-500">NASA GPM IMERG Early · Regional satellite estimate</p>
            <p className="mt-1 text-xs text-slate-500">Observed interval: {time(observation.observed_at)} – {time(observation.interval_end)} IST</p>
            <p className="mt-1 text-xs text-slate-500">Cell centre distance: {observation.distance_km.toFixed(1)} km · Grid: 0.1° (~11 km)</p>
          </>}
    </div>
  )
}
