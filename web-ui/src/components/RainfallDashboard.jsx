import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const PERIODS = ['daily', 'weekly', 'monthly']

export default function RainfallDashboard({ trends, forecast, loading, error, period = 'daily', onPeriodChange, days = 365, onDaysChange }) {
  const records = useMemo(() => {
    if (trends?.period !== period) return []
    return trends.records || []
  }, [trends, period])
  const chartRecords = records.map(item => ({
    ...item,
    label: period === 'monthly' ? item.date : new Date(`${item.date}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }),
  }))
  const available = trends?.available && records.length > 0
  return (
    <section aria-labelledby="rainfall-trends-title" className="citizen-trend border border-[#dfe5df] bg-white p-4">
      <div className="section-kicker">Rainfall context</div>
      <h2 id="rainfall-trends-title" className="mt-1 text-sm font-semibold text-slate-900">Rainfall trends and forecast</h2>
      <p className="mt-1 text-xs text-slate-600">Rainfall can contribute to slope instability alongside terrain, soil, drainage and other conditions. This display does not change the landslide risk assessment.</p>
      <div className="mt-3 flex flex-wrap gap-2" aria-label="Rainfall trend period">
        {PERIODS.map(value => <button key={value} type="button" aria-pressed={period === value} onClick={() => onPeriodChange?.(value)} className="rounded border border-slate-300 px-2 py-1 text-xs capitalize text-slate-700">{value}</button>)}
      </div>
      <div className="mt-2 flex flex-wrap gap-2" aria-label="Historical comparison range">
        {[365, 1825].map(value => <button key={value} type="button" aria-pressed={days === value} onClick={() => onDaysChange?.(value)} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">{value === 365 ? 'Past year' : 'Past 5 years'}</button>)}
      </div>
      {loading ? <p role="status" className="mt-3 text-sm text-slate-600">Loading historical rainfall estimates…</p> : null}
      {error ? <p role="status" className="mt-3 text-sm text-slate-600">Historical rainfall data is currently unavailable.</p> : null}
      {!loading && !error && !available ? <p role="status" className="mt-3 text-sm text-slate-600">No historical observations are available for this location and period.</p> : null}
      {available ? <>
        {trends.accumulation ? <div className="mt-3 flex flex-wrap gap-4 rounded bg-slate-50 p-3 text-sm" aria-label="Latest available rainfall accumulation">
          <div><span className="text-slate-600">Latest complete 7-day accumulation: </span><strong>{trends.accumulation.seven_day_mm == null ? 'Unavailable' : `${trends.accumulation.seven_day_mm} mm`}</strong></div>
          <div><span className="text-slate-600">Latest complete 30-day accumulation: </span><strong>{trends.accumulation.thirty_day_mm == null ? 'Unavailable' : `${trends.accumulation.thirty_day_mm} mm`}</strong></div>
          <p className="w-full text-xs text-slate-500">Available through {trends.accumulation.latest_date || 'unknown date'}; incomplete windows are not totaled.</p>
        </div> : null}
        <div className="mt-3 h-56" role="img" aria-label={`${period} rainfall amounts in millimetres`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartRecords} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" minTickGap={24} />
              <YAxis unit=" mm" />
              <Tooltip formatter={(value, _name, item) => value == null ? ['Missing observation', 'Rainfall'] : [`${value} mm`, `Rainfall · ${item.payload.coverage_days ?? 1} day(s)`]} />
              <Bar dataKey="rainfall_mm" name="Rainfall" fill="#168a73" connectNulls={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-slate-600"><a className="underline" href={trends.attribution_url || 'https://power.larc.nasa.gov/'} target="_blank" rel="noreferrer">{trends.source}</a> · {trends.unit} · grid {trends.resolution} · UTC</p>
        {chartRecords.some(item => item.rainfall_mm == null) ? <p role="status" className="mt-1 text-xs text-amber-800">Missing or incomplete periods are shown without a rainfall amount.</p> : null}
        <p className="mt-1 text-xs text-slate-500">Retrieved by LandSense {trends.updated_at ? new Date(trends.updated_at).toLocaleString() : 'at an unknown time'}. Null values indicate missing data. Recent 105 days are excluded to keep IMERG trend runs consistent.</p>
        {trends.note ? <p className="mt-1 text-xs text-slate-500">{trends.note}</p> : null}
      </> : null}
      <div className="mt-4 border-t border-slate-200 pt-3">
        <h3 className="text-sm font-semibold text-slate-900">Rainfall forecast</h3>
        {forecast?.available && forecast.records?.length ? <>
          <p className="mt-1 text-xs text-slate-600">Forecast · {forecast.source} · {forecast.forecast_start} to {forecast.forecast_end}</p>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{forecast.records.map(item => <div key={item.date} className="rounded border border-blue-200 bg-blue-50 p-2"><div className="text-xs text-slate-600">{item.date}</div><div className="font-semibold text-slate-900">{item.rainfall_mm} mm</div><div className="text-[10px] text-blue-800">Forecast</div></div>)}</div>
          <p className="mt-2 text-xs text-slate-500">{forecast.note} Daily totals are rounded to 0.1 mm. <a className="underline" href={forecast.attribution_url} target="_blank" rel="noreferrer">Weatherbit attribution</a>. Retrieved by LandSense {forecast.updated_at ? new Date(forecast.updated_at).toLocaleString() : 'at an unknown time'}.</p>
        </> : <p role="status" className="mt-1 text-xs text-slate-600">Forecast is unavailable. No future rainfall values are estimated locally.</p>}
      </div>
    </section>
  )
}
