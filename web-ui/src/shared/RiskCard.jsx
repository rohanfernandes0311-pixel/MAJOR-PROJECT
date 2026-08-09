const RISK_CONFIG = {
  SAFE: { color: 'bg-emerald-500', label: 'You are safe' },
  WARNING: { color: 'bg-yellow-500', label: 'Stay alert' },
  'HIGH RISK': { color: 'bg-orange-500', label: 'High risk' },
  CRITICAL: { color: 'bg-red-600', label: 'Extreme' },
  '--': { color: 'bg-slate-600', label: 'Awaiting live update' }
}

export default function RiskCard({ risk = 'SAFE', confidence = 0.9, rainfall = 0, recommendation = 'Monitoring is active' }){
  const config = RISK_CONFIG[risk] || RISK_CONFIG.SAFE
  
  return (
    <div className="rounded-xl bg-white/6 p-4 flex items-center gap-4">
      <div className={`w-20 h-20 rounded-full flex items-center justify-center ${config.color} shadow-lg`} aria-hidden>
        <div className="text-black font-bold">{risk === 'SAFE' ? '✓' : '!'}</div>
      </div>
      <div className="flex-1">
        <div className="text-sm text-slate-200">{config.label}</div>
        <div className="text-lg font-bold mt-1">{risk}</div>
        <div className="mt-1 text-xs text-slate-300">{recommendation}</div>
        <div className="flex gap-4 mt-2 text-sm text-slate-300">
          <div>Confidence: <strong>{Math.round(confidence * 100)}%</strong></div>
          <div>Rainfall: <strong>{rainfall} mm</strong></div>
        </div>
      </div>
      <button className="px-4 py-2 rounded-md bg-emerald-400 text-black font-semibold">Safety plan</button>
    </div>
  )
}
