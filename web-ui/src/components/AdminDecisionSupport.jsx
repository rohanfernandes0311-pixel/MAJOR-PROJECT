import { formatIncidentDate } from '../services/incidentDemo'

const FACTOR_LABELS = {
  rainfall: 'Rainfall',
  historical_activity: 'Historical activity',
  recent_incident: 'Recent incident',
  ml_prediction: 'ML prediction',
  configured_zone: 'Configured zone',
}

function readable(value, fallback = 'NOT AVAILABLE') {
  return value ? String(value).replaceAll('_', ' ').toUpperCase() : fallback
}

function valueOrUnavailable(available, value) {
  return available && value != null ? value : 'Unavailable'
}

function DataQualityNotice({ quality }) {
  if (quality === 'GOOD') return <p className="text-sm font-semibold text-emerald-200">Data quality: GOOD</p>
  if (quality === 'PARTIAL') return <div className="text-sm text-amber-100"><p className="font-semibold">Data quality: PARTIAL</p><p>Some intelligence sources are unavailable.</p></div>
  if (quality === 'LIMITED') return <div className="text-sm text-amber-100"><p className="font-semibold">Data quality: LIMITED</p><p>Decision should be reviewed carefully.</p></div>
  return <div className="text-sm text-rose-100"><p className="font-semibold">Data quality: UNAVAILABLE</p><p>This assessment must not be treated as highly reliable.</p></div>
}

export default function AdminDecisionSupport({
  selectedZoneId,
  selectedZoneName,
  intelligence,
  loading,
  error,
  simulationEnabled,
  simulatedCitizens = [],
  previewLoading,
  onPreview,
}) {
  const assessment = intelligence?.assessment
  const affected = intelligence?.affected
  const affectedAvailable = affected?.status === 'AVAILABLE'
  const simulatedInside = simulatedCitizens.filter((citizen) => citizen.inside !== false).length
  const factors = (assessment?.factors || []).filter((factor) =>
    factor.available && ['rainfall', 'historical_activity', 'recent_incident', 'ml_prediction', 'configured_zone'].includes(factor.factor)
  )
  const supportingFactors = factors.filter((factor) => ['ELEVATED', 'SUPPORTING'].includes(factor.impact))
  const shownFactors = (supportingFactors.length ? supportingFactors : factors).slice(0, 5)
  const risk = readable(assessment?.overallRisk)
  const recommendation = readable(assessment?.recommendedAction)
  const confidence = assessment?.confidence == null ? 'NOT AVAILABLE' : `${(Number(assessment.confidence) * 100).toFixed(1)}%`
  const quality = readable(assessment?.dataQuality, 'UNAVAILABLE')
  const monitorOnly = ['SAFE', 'LOW'].includes(risk) && recommendation === 'MONITOR'
  const actionDisabled = !selectedZoneId || loading || Boolean(error) || !assessment || previewLoading
  const actionLabel = !selectedZoneId
    ? 'Select a configured zone first'
    : loading
      ? 'Loading intelligence...'
      : error || !assessment
        ? 'Decision support unavailable'
        : previewLoading
          ? 'Preparing preview...'
          : 'Preview Targeted Alert'

  return <section aria-labelledby="admin-decision-support-title" className={`admin-decision-card rounded-3xl border bg-[#101725] p-5 ${risk === 'CRITICAL' ? 'border-rose-300/40' : 'border-violet-300/25'}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-xs font-bold tracking-[0.2em] text-violet-200">ADMIN DECISION SUPPORT</p><h2 id="admin-decision-support-title" className="mt-1 text-xl font-bold">{selectedZoneName || 'No configured zone selected'}</h2></div>
      {assessment ? <div className="text-right"><p className="text-xs text-slate-400">OVERALL RISK</p><p className={`mt-1 text-lg font-extrabold ${risk === 'CRITICAL' ? 'text-rose-200' : risk === 'HIGH' ? 'text-orange-200' : risk === 'MEDIUM' ? 'text-amber-100' : 'text-emerald-200'}`}>{risk} RISK</p></div> : null}
    </div>

    {!selectedZoneId ? <div className="mt-5 rounded-xl border border-white/10 bg-black/20 p-4 text-sm text-slate-300"><p>Select a configured zone first.</p><p className="mt-1 text-slate-500">The decision panel, intelligence, affected population, and map will update together.</p></div> : null}
    {selectedZoneId && loading ? <div role="status" className="mt-5 rounded-xl border border-violet-300/20 bg-violet-400/5 p-4 text-sm text-violet-100">Loading intelligence...</div> : null}
    {selectedZoneId && error ? <div role="alert" className="mt-5 rounded-xl border border-rose-300/25 bg-rose-400/10 p-4 text-sm text-rose-100"><p className="font-semibold">Decision support unavailable.</p><p className="mt-1">Please retry or inspect the selected zone.</p></div> : null}

    {assessment && !loading && !error ? <>
      {simulationEnabled ? <div role="status" className="mt-5 rounded-xl border border-orange-300/30 bg-orange-400/10 p-4 text-sm text-orange-100"><p className="font-bold">SIMULATION MODE ACTIVE</p><p className="mt-1">Real alert activation is disabled.</p></div> : null}

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl bg-black/20 p-3"><p className="text-xs text-slate-400">RISK</p><p className="mt-1 font-bold">{risk}</p></div>
        <div className="rounded-xl bg-black/20 p-3"><p className="text-xs text-slate-400">CONFIDENCE</p><p className="mt-1 font-bold">{confidence}</p></div>
        <div className="rounded-xl bg-black/20 p-3"><p className="text-xs text-slate-400">DATA QUALITY</p><p className="mt-1 font-bold">{quality}</p></div>
        <div className="rounded-xl bg-black/20 p-3"><p className="text-xs text-slate-400">RECOMMENDED ACTION</p><p className="mt-1 font-bold">{recommendation}</p></div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold">WHY THIS REQUIRES ATTENTION</h3>
          <div className="mt-3 space-y-2">{shownFactors.length ? shownFactors.map((factor) => <details key={factor.factor} className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-sm"><summary className="flex cursor-pointer items-center justify-between gap-3"><span>{FACTOR_LABELS[factor.factor] || factor.factor}</span><span className="font-bold text-violet-200">{readable(factor.status)}</span></summary><p className="mt-2 border-t border-white/8 pt-2 text-xs text-slate-400">{factor.explanation}</p></details>) : <p className="rounded-xl bg-black/20 p-3 text-sm text-slate-400">No supporting factors are currently available.</p>}</div>
        </div>
        <div>
          <h3 className="text-sm font-semibold">AFFECTED POPULATION</h3>
          <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-xl bg-black/20 p-3"><p className="text-slate-400">Real users inside</p><p className="mt-1 text-lg font-bold">{valueOrUnavailable(affectedAvailable, affected?.insideUsers)}</p></div>
            <div className="rounded-xl bg-black/20 p-3"><p className="text-slate-400">Real users outside</p><p className="mt-1 text-lg font-bold">{valueOrUnavailable(affectedAvailable, affected?.outsideUsers)}</p></div>
            <div className="rounded-xl bg-black/20 p-3"><p className="text-slate-400">Eligible recipients</p><p className="mt-1 text-lg font-bold text-cyan-200">{valueOrUnavailable(affectedAvailable, affected?.recipientCount)}</p></div>
            <div className="rounded-xl bg-black/20 p-3"><p className="text-slate-400">SMS eligible</p><p className="mt-1 text-lg font-bold">{valueOrUnavailable(affectedAvailable, affected?.smsEligibleCount)}</p></div>
          </div>
          {!affectedAvailable ? <p className="mt-3 text-sm text-amber-100">Affected population unavailable. Risk assessment remains available, but recipient preview uses the existing authoritative Phase 5 flow.</p> : null}
          {simulationEnabled ? <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl border border-orange-300/20 bg-orange-400/5 p-3 text-sm"><div><p className="text-xs font-bold text-emerald-200">REAL</p><p className="mt-1">{valueOrUnavailable(affectedAvailable, affected?.recipientCount)} recipients</p></div><div><p className="text-xs font-bold text-orange-200">SIMULATION</p><p className="mt-1">{simulatedInside} demo participants</p></div></div> : null}
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-white/10 bg-black/15 p-4"><DataQualityNotice quality={quality} /></div>

      <div className="mt-5 rounded-xl border border-violet-300/20 bg-violet-400/10 p-4">
        <h3 className="text-xs font-bold tracking-[0.18em] text-violet-200">DECISION SUMMARY</h3>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3"><div><dt className="text-slate-400">Risk</dt><dd className="font-bold">{risk}</dd></div><div><dt className="text-slate-400">Evidence</dt><dd className="font-bold">{supportingFactors.length} supporting factors</dd></div><div><dt className="text-slate-400">Confidence</dt><dd className="font-bold">{confidence}</dd></div><div><dt className="text-slate-400">Data quality</dt><dd className="font-bold">{quality}</dd></div><div><dt className="text-slate-400">Affected users</dt><dd className="font-bold">{valueOrUnavailable(affectedAvailable, affected?.insideUsers)}</dd></div><div><dt className="text-slate-400">Recommended action</dt><dd className="font-bold">{recommendation}</dd></div></dl>
      </div>

      <div className="mt-5"><h3 className="text-sm font-semibold">RECENT INCIDENT</h3>{intelligence.recentIncident ? <div className="mt-2 rounded-xl border border-orange-300/20 bg-orange-400/5 p-3 text-sm"><p className="font-bold">{intelligence.recentIncident.title}</p><p className="mt-1">Status: {readable(intelligence.recentIncident.status)}</p><p className="mt-1">Date: {formatIncidentDate(intelligence.recentIncident.date)}</p><p className="mt-1">Location precision: {readable(intelligence.recentIncident.location_precision)}</p></div> : <p className="mt-2 text-sm text-slate-400">Recent incident: None identified. This is not evidence that the area is safe.</p>}</div>

      <div className="mt-5 rounded-xl border border-amber-300/25 bg-amber-400/10 p-4 text-sm text-amber-50"><p className="font-bold">ADMIN REVIEW REQUIRED</p><p className="mt-1">LandSense provides a risk assessment and recommendation. Alert activation requires explicit Admin confirmation.</p></div>
      {monitorOnly ? <p className="mt-4 rounded-xl border border-emerald-300/20 bg-emerald-400/5 p-3 text-sm text-emerald-100">No immediate alert action recommended.</p> : null}
      {risk === 'CRITICAL' ? <a href="#incident-intelligence-map" className="mt-4 inline-flex rounded-xl border border-rose-300/30 px-4 py-2 text-sm font-semibold text-rose-100">Review affected area</a> : null}
    </> : null}

    <button
      type="button"
      onClick={onPreview}
      disabled={actionDisabled || monitorOnly}
      data-zone-id={selectedZoneId || ''}
      data-risk={assessment?.overallRisk || ''}
      data-recommendation={assessment?.recommendedAction || ''}
      className={`mt-5 w-full rounded-xl px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${monitorOnly ? 'border border-white/15 text-slate-300' : 'bg-cyan-300 text-slate-950'}`}
    >{monitorOnly ? 'Monitoring - no alert preview recommended' : actionLabel}</button>
    <p className="mt-2 text-xs text-slate-500">Uses the existing Phase 5 recipient preview. It never sends or activates an alert. Automatic alert: {assessment?.automaticAlert === false ? 'OFF' : 'UNAVAILABLE'}.</p>
  </section>
}
