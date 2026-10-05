import { useMemo, useState } from 'react'

const FILTERS = ['ALL', 'INTELLIGENCE', 'ADMIN_ACTION', 'INCIDENT', 'ALERT', 'SIMULATION']
const DETAIL_LABELS = {
  confidence: 'Confidence', dataQuality: 'Data quality', recommendedAction: 'Recommended action',
  automaticAlert: 'Automatic alert', affectedStatus: 'Affected status', realUsersInside: 'Real users inside',
  realUsersOutside: 'Real users outside', eligibleRecipients: 'Eligible recipients',
  smsEligibleRecipients: 'SMS eligible', totalRegisteredUsers: 'Registered users', recipientCount: 'Recipients',
  status: 'Status', smsRequested: 'SMS requested', smsSent: 'SMS sent', smsFailed: 'SMS failed',
  smsSuppressed: 'SMS suppressed', incidentTitle: 'Incident', incidentStatus: 'Incident status',
  sourceLabel: 'Source', locationPrecision: 'Location precision', simulatedParticipants: 'Demo participants',
  reason: 'Reason', scenarioName: 'Scenario', forcedRisk: 'Simulated risk',
  externalNotificationsSuppressed: 'External notifications suppressed',
  channels: 'Demo channels', smsDemoCount: 'SMS demo count',
  bluetoothDemoCount: 'Bluetooth demo count', realSmsCount: 'Real SMS count',
  realBluetoothCount: 'Real Bluetooth count', realAlertCount: 'Real alert count',
  offlineDeliverySimulation: 'Offline delivery simulation',
}

function localTime(value) {
  if (!value) return 'Time unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString()
}

function readable(value) {
  return String(value ?? 'Unavailable').replaceAll('_', ' ')
}

export default function AdminAuditTimeline({ events, loading, error, hasMore, loadingMore, onRetry, onLoadMore }) {
  const [filter, setFilter] = useState('ALL')
  const orderedEvents = useMemo(() => [...(events || [])].sort((a, b) => {
    const byTime = new Date(b.timestampUtc).getTime() - new Date(a.timestampUtc).getTime()
    return Number.isFinite(byTime) && byTime !== 0 ? byTime : String(b.eventId).localeCompare(String(a.eventId))
  }), [events])
  const visibleEvents = filter === 'ALL' ? orderedEvents : orderedEvents.filter((event) => event.category === filter)

  return <section aria-labelledby="admin-audit-title" className="rounded-3xl border border-cyan-300/15 bg-[#0c1724] p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold tracking-[0.2em] text-cyan-200">ADMIN AUDIT</p><h2 id="admin-audit-title" className="mt-1 text-xl font-bold">Event timeline</h2><p className="mt-1 text-xs text-slate-400">Historical operations only. The current Decision Support panel remains authoritative for the present state.</p></div><span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300">Newest first</span></div>
    <div className="mt-4 flex flex-wrap gap-2" aria-label="Audit category filter">{FILTERS.map((name) => <button key={name} type="button" aria-pressed={filter === name} onClick={() => setFilter(name)} className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${filter === name ? 'border-cyan-300/40 bg-cyan-400/15 text-cyan-100' : 'border-white/10 text-slate-400'}`}>{readable(name)}</button>)}</div>

    {loading ? <p role="status" className="mt-5 rounded-xl border border-white/10 bg-black/15 p-4 text-sm text-slate-300">Loading audit events...</p> : null}
    {error ? <div role="alert" className="mt-5 rounded-xl border border-rose-300/25 bg-rose-400/10 p-4 text-sm text-rose-100"><p>Audit timeline unavailable.</p><button type="button" onClick={onRetry} className="mt-3 rounded-lg border border-rose-200/30 px-3 py-1.5 font-semibold">Retry</button></div> : null}
    {!loading && !error && !orderedEvents.length ? <p className="mt-5 rounded-xl border border-white/10 bg-black/15 p-4 text-sm text-slate-400">No audit events yet.</p> : null}
    {!loading && !error && orderedEvents.length > 0 && !visibleEvents.length ? <p className="mt-5 rounded-xl border border-white/10 bg-black/15 p-4 text-sm text-slate-400">No audit events are available for this filter.</p> : null}

    {!loading && !error && visibleEvents.length ? <ol className="mt-5 space-y-3">{visibleEvents.map((event) => {
      const details = Object.entries(event.metadata || {}).filter(([key]) => DETAIL_LABELS[key])
      return <li key={event.eventId} className={`rounded-2xl border p-4 ${event.mode === 'REAL' ? 'border-emerald-300/15 bg-emerald-400/[0.03]' : 'border-orange-300/20 bg-orange-400/5'}`}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-slate-500">{localTime(event.timestampUtc)}</p><h3 className="mt-1 font-bold">{readable(event.eventType)}</h3><p className="mt-1 text-sm text-slate-300">{event.zoneName || event.metadata?.incidentTitle || 'LandSense Admin'}</p></div><div className="flex flex-wrap gap-2">{event.risk ? <span className="rounded-full border border-white/10 px-2 py-1 text-xs font-bold">{event.risk}</span> : null}<span className={`rounded-full border px-2 py-1 text-xs font-bold ${event.mode === 'REAL' ? 'border-emerald-300/25 text-emerald-200' : 'border-orange-300/30 text-orange-200'}`}>{event.mode}</span></div></div>
        <p className="mt-2 text-sm text-slate-400">{event.message}</p>
        {details.length || event.zoneId ? <details className="mt-3 rounded-xl border border-white/8 bg-black/15 p-3 text-sm"><summary className="cursor-pointer font-semibold">Event details</summary><dl className="mt-3 grid gap-2 sm:grid-cols-2">{event.zoneId ? <div><dt className="text-xs text-slate-500">Configured zone</dt><dd>{event.zoneName || event.zoneId}</dd></div> : null}{details.map(([key, value]) => <div key={key}><dt className="text-xs text-slate-500">{DETAIL_LABELS[key]}</dt><dd>{typeof value === 'boolean' ? value ? 'YES' : key === 'automaticAlert' ? 'OFF' : 'NO' : readable(value)}</dd></div>)}</dl></details> : null}
      </li>
    })}</ol> : null}
    {!loading && !error && hasMore ? <button type="button" onClick={onLoadMore} disabled={loadingMore} className="mt-4 w-full rounded-xl border border-cyan-300/20 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50">{loadingMore ? 'Loading more...' : 'Load more events'}</button> : null}
  </section>
}
