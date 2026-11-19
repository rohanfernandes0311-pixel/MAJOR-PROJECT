const RISK_CONFIG = {
  SAFE: { color: 'bg-emerald-600', label: 'Safe conditions', advice: 'No configured risk zone detected nearby.' },
  LOW: { color: 'bg-emerald-600', label: 'Low risk conditions', advice: 'Continue monitoring local safety guidance.' },
  'MEDIUM RISK': { color: 'bg-amber-500', label: 'Stay alert', advice: 'Monitor updates and avoid vulnerable slopes.' },
  'HIGH RISK': { color: 'bg-red-600', label: 'Avoid vulnerable areas', advice: 'Follow safety guidance and prepare to move.' },
  'CRITICAL RISK': { color: 'bg-red-800', label: 'Move to a safer location', advice: 'Follow evacuation and official guidance now.' },
  '--': { color: 'bg-slate-500', label: 'Checking your location', advice: 'Risk status will appear after a location update.' }
}

export default function RiskCard({ risk = 'SAFE', confidence = 0.9, rainfall = 0, recommendation = 'Monitoring is active', updated = 'Not yet' }) {
  const config = RISK_CONFIG[risk] || RISK_CONFIG.SAFE

  return (
    <section aria-label="Current landslide risk" data-risk={risk} className="risk-card ls-card flex items-start gap-4 p-4 sm:p-5">
      <div className={`h-14 w-2 shrink-0 rounded-full ${config.color}`} aria-hidden />
      <div className="flex-1">
        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Current landslide risk</div>
        <div className="risk-card-value mt-1 text-2xl font-bold">{risk}</div>
        <div className="mt-1 text-sm font-medium text-slate-700">{config.label}</div>
        <div className="mt-1 text-sm text-slate-500">{config.advice || recommendation}</div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
          <div>Model score <strong className="text-slate-700">{Math.round(confidence * 100)}%</strong></div>
          <div>Rainfall <strong className="text-slate-700">{rainfall} mm</strong></div>
        </div>
        <div className="mt-3 border-t border-slate-200 pt-2 text-[11px] text-slate-500">Model score is not a calibrated real-world probability · Updated {updated}</div>
      </div>
    </section>
  )
}
