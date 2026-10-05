import React from 'react'

export default function SoilMoistureCard({ observation, loading = false }) {
  return (
    <div aria-busy={loading}>
      <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Surface Soil Moisture</div>
      {loading ? <p role="status" className="mt-2 text-sm">Loading satellite data…</p>
        : !observation ? <p role="status" className="mt-2 text-sm">Live data unavailable.</p>
          : <>
            <div className="mt-2 text-xl font-semibold">{observation.soil_moisture_percent.toFixed(2)}%</div>
            <div className="text-xs text-slate-600">Water by volume</div>
            <p className="mt-1 text-xs text-slate-500">Latest available satellite observation</p>
            <p className="mt-2 text-xs text-slate-500">NASA SMAP NRT · Regional satellite estimate</p>
            <p className="mt-1 text-xs text-slate-500">Observed: {new Date(observation.observed_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })} IST</p>
            <p className="mt-1 text-xs text-slate-500">Cell centre distance: {observation.distance_km.toFixed(1)} km · Resolution: ~{observation.spatial_resolution_km} km · Depth: ~0–5 cm</p>
          </>}
    </div>
  )
}
