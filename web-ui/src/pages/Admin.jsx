import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, LogOut, MapPin, RefreshCw, ShieldCheck, Users } from 'lucide-react'
import MapView from '../shared/MapView'
import { apiFetch } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { INCIDENT_SCENARIO_LABEL, INCIDENT_SCENARIOS, getIncidentScenario } from '../data/incidentScenarios'
import { buildDemoAlert, buildSimulatedSms, clearDemoAlert, formatIncidentDate, generateSimulatedCitizens, impactLines, previewSimulatedRecipients, saveDemoAlert } from '../services/incidentDemo'
import { buildAdminIntelligence } from '../services/adminIntelligence'
import AdminAuditTimeline from '../components/AdminAuditTimeline'
import AdminOfflineAlertDemo from '../components/AdminOfflineAlertDemo'
import AdminHttpsmsExport from '../components/AdminHttpsmsExport'
import AdminKodaguSimulation from '../components/AdminKodaguSimulation'

const RISK_ORDER = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
const SIMULATION_SCENARIOS = [
  { name: 'Normal', risk: 'LOW' }, { name: 'Medium Risk', risk: 'MEDIUM' },
  { name: 'High Risk', risk: 'HIGH' }, { name: 'Critical Emergency', risk: 'CRITICAL' }
]
const DEFAULT_AFFECTED_MESSAGE = 'Please review local safety conditions and follow official guidance.'

function RiskPill({ value }) {
  const level = String(value || 'LOW').toUpperCase()
  const colors = {
    LOW: 'border-emerald-300/25 bg-emerald-400/10 text-emerald-200',
    MEDIUM: 'border-amber-300/25 bg-amber-400/10 text-amber-100',
    HIGH: 'border-orange-300/25 bg-orange-400/10 text-orange-100',
    CRITICAL: 'border-rose-300/25 bg-rose-400/10 text-rose-100'
  }
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-bold tracking-wide ${colors[level] || colors.LOW}`}>{level}</span>
}

function displayTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function SourceState({ value }) {
  const state = String(value || 'UNAVAILABLE').toUpperCase()
  const tone = state === 'REAL' || state === 'AVAILABLE' || state.startsWith('VERIFIED')
    ? 'text-emerald-200'
    : state === 'SIMULATED' || state.includes('REVIEW') || state === 'PARTIAL'
      ? 'text-amber-200'
      : 'text-slate-400'
  return <span className={`text-xs font-bold ${tone}`}>{state}</span>
}

function AffectedPopulationCard({ affected, realRecipientCount, simulatedCitizens, simulationEnabled, onPreview, previewLoading }) {
  const simulatedInside = simulatedCitizens.filter((citizen) => citizen.inside !== false).length
  const simulatedOutside = simulatedCitizens.length - simulatedInside
  const available = affected?.status === 'AVAILABLE'
  const count = (value) => available && value != null ? value : 'Unavailable'
  return <div className="rounded-2xl border border-emerald-300/20 bg-emerald-400/5 p-4">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-xs font-bold tracking-[0.18em] text-emerald-200">AFFECTED POPULATION</p><p className="mt-1 text-sm text-slate-400">Population does not change the hazard risk level.</p></div><SourceState value={affected?.status} /></div>
    <div className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3"><div className="rounded-lg bg-black/15 p-3"><p className="text-slate-400">Real users inside</p><p className="mt-1 text-xl font-bold text-emerald-200">{count(affected?.insideUsers)}</p></div><div className="rounded-lg bg-black/15 p-3"><p className="text-slate-400">Real users outside</p><p className="mt-1 text-xl font-bold">{count(affected?.outsideUsers)}</p></div><div className="rounded-lg bg-black/15 p-3"><p className="text-slate-400">Real alert recipients</p><p className="mt-1 text-xl font-bold text-cyan-200">{count(realRecipientCount)}</p></div><div className="rounded-lg border border-orange-300/10 bg-orange-400/5 p-3"><p className="text-slate-400">Simulated citizens</p><p className="mt-1 text-xl font-bold text-orange-200">{simulationEnabled ? simulatedCitizens.length : 0}</p></div><div className="rounded-lg border border-orange-300/10 bg-orange-400/5 p-3"><p className="text-slate-400">Simulated inside</p><p className="mt-1 text-xl font-bold text-orange-200">{simulationEnabled ? simulatedInside : 0}</p></div><div className="rounded-lg border border-orange-300/10 bg-orange-400/5 p-3"><p className="text-slate-400">Simulated outside</p><p className="mt-1 text-xl font-bold">{simulationEnabled ? simulatedOutside : 0}</p></div></div>
    {available && affected.insideUsers === 0 ? <p className="mt-3 text-sm text-slate-300">No current users with recorded locations are inside this configured zone.</p> : null}
    {affected?.users?.length ? <details className="mt-3 rounded-xl border border-white/8 bg-black/10 p-3"><summary className="cursor-pointer text-sm font-semibold">View located users ({affected.users.length})</summary><div className="mt-3 grid gap-2 sm:grid-cols-2">{affected.users.map((user) => <div key={user.displayId} className="flex items-center justify-between gap-3 rounded-lg bg-black/20 px-3 py-2 text-xs"><span>{user.displayId}<span className="mt-0.5 block text-[10px] text-slate-500">Recorded {displayTime(user.lastUpdated)}</span></span><span className={user.inside ? 'font-bold text-emerald-200' : 'text-slate-400'}>{user.status}</span></div>)}</div></details> : null}
    <button type="button" onClick={onPreview} disabled={!available || previewLoading} className="mt-4 w-full rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">{previewLoading ? 'Preparing preview…' : 'Preview targeted alert'}</button>
    <p className="mt-2 text-xs text-slate-500">Uses the existing Phase 5 server preview. Automatic alert: OFF.</p>
  </div>
}

function IntelligenceCard({ intelligence, loading, error, realRecipientCount, simulatedCitizens, simulationEnabled, onPreview, previewLoading }) {
  if (loading) return <section className="admin-intelligence-card rounded-3xl border border-violet-300/20 bg-[#111526] p-5 text-sm text-violet-100">Loading environmental and historical intelligence…</section>
  if (error) return <section className="admin-intelligence-card rounded-3xl border border-amber-300/20 bg-[#111526] p-5"><h2 className="font-semibold">Landslide intelligence</h2><p className="mt-2 text-sm text-amber-100">{error}</p></section>
  if (!intelligence) return null
  const values = intelligence.environmentalValues || {}
  const incident = intelligence.recentIncident
  const assessment = intelligence.assessment || {}
  const factorLabels = { rainfall: 'Rainfall', humidity: 'Humidity', temperature: 'Temperature', wind: 'Wind', historical_activity: 'Historical activity', recent_incident: 'Recent incident', ml_prediction: 'ML prediction', configured_zone: 'Configured zone' }
  const primaryFactors = (assessment.factors || []).filter((factor) => ['rainfall', 'historical_activity', 'recent_incident', 'ml_prediction', 'configured_zone'].includes(factor.factor))
  const confidenceText = assessment.confidence == null ? 'NOT AVAILABLE' : `${(Number(assessment.confidence) * 100).toFixed(1)}%`
  const actionText = String(assessment.recommendedAction || 'MONITOR').replaceAll('_', ' ')

  return <section className="admin-intelligence-card rounded-3xl border border-violet-300/25 bg-[#111526] p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold tracking-[0.2em] text-violet-200">LANDSLIDE INTELLIGENCE</p><h2 className="mt-1 text-xl font-bold">{intelligence.zone?.name}</h2><p className="mt-1 text-xs text-slate-400">Decision support only · no alert is activated by this card</p></div><div className="text-right"><p className="text-xs text-slate-400">Overall risk</p><div className="mt-1"><RiskPill value={assessment.overallRisk} /></div><p className="mt-2 text-[11px] text-slate-500">Basis: {intelligence.overallRiskBasis}</p></div></div>
    <div className="mt-5">
      <p className="section-kicker">Environmental signals</p>
      <div className="admin-environmental-signals mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(values).map(([name, item]) => <div key={name} className="admin-signal rounded-xl border border-white/8 bg-white/[0.03] p-3"><p className="text-xs uppercase tracking-wide text-slate-400">{name}</p><p className="mt-1 text-lg font-bold">{item?.status === 'UNAVAILABLE' || item?.value == null ? 'Unavailable' : `${Number(item.value).toFixed(1)} ${item.unit}`}</p><SourceState value={item?.status} /></div>)}</div>
    </div>
    <div className="mt-5 grid gap-5 lg:grid-cols-2">
      <div><h3 className="text-sm font-semibold">Why is this risk elevated?</h3><div className="mt-3 space-y-2 text-sm text-slate-300">{primaryFactors.length ? primaryFactors.map((factor) => <details key={factor.factor} className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2"><summary className="flex cursor-pointer list-none items-center justify-between gap-3"><span>{factorLabels[factor.factor] || factor.factor}</span><span className="flex items-center gap-2"><SourceState value={factor.status} /><span className="text-[11px] text-slate-500">{factor.impact}</span></span></summary><div className="mt-2 border-t border-white/8 pt-2 text-xs text-slate-400">{factor.value != null && factor.factor !== 'ml_prediction' && factor.factor !== 'configured_zone' ? <p className="mb-1">Value: {factor.value} {factor.unit || ''}</p> : null}<p>{factor.explanation}</p></div></details>) : <p>No explanatory factors are currently available.</p>}</div><div className="mt-4 rounded-xl border border-violet-300/20 bg-violet-400/10 p-3"><p className="text-xs text-violet-200">RECOMMENDED ACTION</p><p className="mt-1 font-bold">{actionText}</p><p className="mt-1 text-xs text-slate-400">Advisory only. Admin review is required before using the existing Phase 5 workflow.</p></div></div>
      <div><h3 className="text-sm font-semibold">Assessment quality</h3><div className="mt-3 space-y-2 text-sm">{[['Confidence', confidenceText], ['Data quality', assessment.dataQuality], ['Weather source', intelligence.weatherSource], ['Historical inventory', intelligence.historicalContext?.status], ['Recent incidents', intelligence.recentIncidentStatus], ['ML prediction', intelligence.mlRisk?.status], ['GPS', 'ADMIN CONTEXT'], ['Automatic alert', assessment.automaticAlert === false ? 'OFF' : 'UNAVAILABLE']].map(([label, status]) => <div key={label} className="flex items-center justify-between gap-3 rounded-lg bg-black/15 px-3 py-2"><span className="text-slate-300">{label}</span><SourceState value={status} /></div>)}</div><p className="mt-3 text-xs text-slate-400">Historical landslides inside zone: {intelligence.historicalContext?.status === 'AVAILABLE' ? intelligence.historicalContext.nearby_count : 'Unavailable'} · historical context only</p></div>
    </div>
    <div className="mt-5"><AffectedPopulationCard affected={intelligence.affected} realRecipientCount={realRecipientCount} simulatedCitizens={simulatedCitizens} simulationEnabled={simulationEnabled} onPreview={onPreview} previewLoading={previewLoading} /></div>
    <div className="mt-5 border-t border-white/10 pt-4"><h3 className="text-sm font-semibold">Recent incident context</h3>{incident ? <div className="mt-3 rounded-xl border border-orange-300/20 bg-orange-400/5 p-3 text-sm"><div className="flex flex-wrap justify-between gap-2"><b>{incident.title}</b><SourceState value={incident.status} /></div><p className="mt-2 text-slate-300">Date: {formatIncidentDate(incident.date)}</p><p className="mt-1 text-slate-300">Location: {incident.location_name}, {incident.district} · {incident.location_precision}</p><p className="mt-1 text-slate-300">Classification: {incident.classification}</p><p className="mt-1 text-slate-300">Source: <a href={incident.source_url} target="_blank" rel="noreferrer" className="text-cyan-200 underline">{incident.source_label}</a></p></div> : <p className="mt-2 text-sm text-slate-400">NONE IDENTIFIED. Absence of a matched scenario is not evidence of safety.</p>}</div>
  </section>
}

export default function Admin() {
  const { token, profile, signOut } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState({ stats: null, users: [], alerts: [], events: [], landslides: [] })
  const [zones, setZones] = useState([])
  const [loading, setLoading] = useState(true)
  const [zoneLoading, setZoneLoading] = useState(true)
  const [error, setError] = useState('')
  const [zoneLoadError, setZoneLoadError] = useState('')
  const [simulation, setSimulation] = useState({ enabled: false, effective_risk: 'LOW', scenario_name: 'Normal' })
  const [selectedScenario, setSelectedScenario] = useState(SIMULATION_SCENARIOS[0])
  const [simulationSaving, setSimulationSaving] = useState(false)
  const [selectedConfiguredZone, setSelectedConfiguredZone] = useState('')
  const [selectedIncidentScenario, setSelectedIncidentScenario] = useState('')
  const [affectedRisk, setAffectedRisk] = useState('HIGH')
  const [affectedMessage, setAffectedMessage] = useState(DEFAULT_AFFECTED_MESSAGE)
  const [affectedDuration, setAffectedDuration] = useState(60)
  const [recipientPreview, setRecipientPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [activationConfirm, setActivationConfirm] = useState(false)
  const [activationLoading, setActivationLoading] = useState(false)
  const [activationResult, setActivationResult] = useState(null)
  const [sendSms, setSendSms] = useState(false)
  const [simulateCitizens, setSimulateCitizens] = useState(false)
  const [insideCitizenCount, setInsideCitizenCount] = useState(12)
  const [outsideCitizenCount, setOutsideCitizenCount] = useState(3)
  const [demoRecipientPreview, setDemoRecipientPreview] = useState(null)
  const [demoLaunchResult, setDemoLaunchResult] = useState(null)
  const [zoneIntelligence, setZoneIntelligence] = useState(null)
  const [intelligenceLoading, setIntelligenceLoading] = useState(false)
  const [intelligenceError, setIntelligenceError] = useState('')
  const [auditEvents, setAuditEvents] = useState([])
  const [auditLoading, setAuditLoading] = useState(true)
  const [auditLoadingMore, setAuditLoadingMore] = useState(false)
  const [auditError, setAuditError] = useState('')
  const [auditHasMore, setAuditHasMore] = useState(false)
  const [offlineDemoPreview, setOfflineDemoPreview] = useState(null)
  const [offlineDemoChannels, setOfflineDemoChannels] = useState({ sms: true, bluetooth: true })
  const [offlineDemoConfirmed, setOfflineDemoConfirmed] = useState(false)
  const [offlineDemoLoading, setOfflineDemoLoading] = useState(false)
  const [offlineDemoResult, setOfflineDemoResult] = useState(null)

  const loadAuditEvents = useCallback(async (offset = 0) => {
    if (offset === 0) setAuditLoading(true)
    else setAuditLoadingMore(true)
    setAuditError('')
    try {
      const response = await apiFetch(`/admin/audit/events?limit=50&offset=${offset}`, {}, token)
      const incoming = Array.isArray(response?.events) ? response.events : []
      setAuditEvents((current) => offset === 0 ? incoming : [...current, ...incoming.filter((event) => !current.some((item) => item.eventId === event.eventId))])
      setAuditHasMore(Boolean(response?.hasMore))
    } catch {
      setAuditError('Audit history could not be loaded.')
    } finally {
      setAuditLoading(false)
      setAuditLoadingMore(false)
    }
  }, [token])

  const recordUiAuditEvent = useCallback(async (payload) => {
    try {
      const response = await apiFetch('/admin/audit/events', { method: 'POST', body: JSON.stringify(payload) }, token)
      if (response?.event) setAuditEvents((current) => [response.event, ...current.filter((item) => item.eventId !== response.event.eventId)])
    } catch {
      // Audit degradation must not turn a selection or safe demo into an alert action.
    }
  }, [token])

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [stats, users, alerts, events, simulationState, inventory] = await Promise.all([
        apiFetch('/admin/stats', {}, token),
        apiFetch('/admin/users?limit=12', {}, token),
        apiFetch('/admin/alerts?limit=8', {}, token),
        apiFetch('/admin/events?limit=12', {}, token),
        apiFetch('/admin/simulation/state', {}, token),
        apiFetch('/landslides?limit=2000', {}, token).catch(() => ({ landslides: [] }))
      ])
      setData({ stats, users: users.users || [], alerts: alerts.alerts || [], events: events.events || [], landslides: inventory.landslides || [] })
      setSimulation(simulationState)
    } catch (err) {
      setError(err?.status === 403 ? 'Your account is not authorized for the command centre.' : 'Unable to load live administration data.')
    } finally {
      setLoading(false)
    }
  }, [token])

  const loadConfiguredZones = useCallback(async () => {
    setZoneLoading(true)
    setZoneLoadError('')
    try {
      const response = await apiFetch('/zones', {}, token)
      const configuredZones = Array.isArray(response?.features) ? response.features : []
      setZones(configuredZones)
      setSelectedConfiguredZone((current) => configuredZones.some((zone) => String(zone?.properties?.zone_id || '') === current) ? current : '')
    } catch {
      setZones([])
      setSelectedConfiguredZone('')
      setZoneLoadError('Configured risk zones could not be loaded. Recipient preview and activation are unavailable until the zone service recovers.')
    } finally {
      setZoneLoading(false)
    }
  }, [token])

  const refreshDashboard = useCallback(() => {
    void loadDashboard()
    void loadConfiguredZones()
    void loadAuditEvents(0)
  }, [loadAuditEvents, loadConfiguredZones, loadDashboard])

  useEffect(() => {
    void loadDashboard()
    void loadConfiguredZones()
    void loadAuditEvents(0)
  }, [loadAuditEvents, loadConfiguredZones, loadDashboard])

  const selectedIncident = useMemo(() => getIncidentScenario(selectedIncidentScenario), [selectedIncidentScenario])
  const affectedZoneId = selectedConfiguredZone

  const simulationLocation = simulation.enabled && simulation.danger_latitude != null && simulation.danger_longitude != null
      ? { lat: simulation.danger_latitude, lng: simulation.danger_longitude, label: simulation.danger_zone_name || simulation.scenario_name }
      : null

  const simulatedCitizenLocations = useMemo(
    () => simulateCitizens && selectedIncident ? generateSimulatedCitizens(selectedIncident, insideCitizenCount, outsideCitizenCount) : [],
    [simulateCitizens, selectedIncident, insideCitizenCount, outsideCitizenCount]
  )
  const displayedSimulatedCitizens = useMemo(
    () => simulation.enabled ? (demoRecipientPreview?.citizens || simulatedCitizenLocations) : [],
    [demoRecipientPreview, simulatedCitizenLocations, simulation.enabled]
  )
  const realAffectedUsers = useMemo(() => zoneIntelligence?.affected?.users || [], [zoneIntelligence])
  const realRecipientCount = zoneIntelligence?.affected?.recipientCount ?? 0

  const selectedConfiguredZoneGeometry = useMemo(
    () => zones.find((zone) => String(zone?.properties?.zone_id || '') === affectedZoneId) || null,
    [zones, affectedZoneId]
  )

  useEffect(() => {
    let active = true
    if (!selectedConfiguredZone || !selectedConfiguredZoneGeometry) {
      setZoneIntelligence(null)
      setIntelligenceError('')
      setIntelligenceLoading(false)
      return () => { active = false }
    }
    setIntelligenceLoading(true)
    setIntelligenceError('')
    setZoneIntelligence(null)
    apiFetch(`/admin/intelligence/zones/${encodeURIComponent(selectedConfiguredZone)}`, {}, token)
      .then((response) => { if (active) { setZoneIntelligence(buildAdminIntelligence(response)); void loadAuditEvents(0) } })
      .catch(() => { if (active) { setZoneIntelligence(null); setIntelligenceError('Intelligence sources are temporarily unavailable. Configured-zone selection and alert controls remain unchanged.') } })
      .finally(() => { if (active) setIntelligenceLoading(false) })
    return () => { active = false }
  }, [loadAuditEvents, selectedConfiguredZone, selectedConfiguredZoneGeometry, token])

  const activeMapIncident = useMemo(() => {
    if (!simulation.enabled || !selectedIncident) return null
    const latitude = Number(selectedIncident.latitude)
    const longitude = Number(selectedIncident.longitude)
    return Number.isFinite(latitude) && Number.isFinite(longitude) ? selectedIncident : null
  }, [selectedIncident, simulation.enabled])

  const contextualMapIncident = selectedConfiguredZone ? zoneIntelligence?.recentIncident || null : null
  const mapIncident = activeMapIncident || contextualMapIncident
  const incidentDemoMode = Boolean(activeMapIncident)
  const mapIncidentLocation = useMemo(() => {
    if (!mapIncident) return null
    const latitude = Number(mapIncident.latitude)
    const longitude = Number(mapIncident.longitude)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
    return {
      id: mapIncident.id,
      lat: latitude,
      lng: longitude,
      title: mapIncident.title,
      location: `${mapIncident.location_name}, ${mapIncident.district} · ${String(mapIncident.location_precision || 'approximate').toUpperCase()} location`,
      date: formatIncidentDate(mapIncident.date),
      risk: mapIncident.demo_risk,
      status: incidentDemoMode ? 'Active simulation' : mapIncident.status,
      classification: mapIncident.classification || `${mapIncident.demo_risk} — DEMO CLASSIFICATION`,
      sourceLabel: mapIncident.source_label,
    }
  }, [incidentDemoMode, mapIncident])
  const mapContext = useMemo(() => selectedConfiguredZoneGeometry ? {
    zoneName: selectedConfiguredZoneGeometry.properties?.name || selectedConfiguredZone,
    risk: zoneIntelligence?.assessment?.overallRisk || selectedConfiguredZoneGeometry.properties?.risk_level,
    insideUsers: zoneIntelligence?.affected?.insideUsers,
    recipientCount: zoneIntelligence?.affected?.recipientCount,
    incidentStatus: zoneIntelligence?.recentIncident ? 'YES' : 'NONE IDENTIFIED',
  } : null, [selectedConfiguredZone, selectedConfiguredZoneGeometry, zoneIntelligence])

  const adminMapKey = [
    simulation.enabled ? 'simulation-on' : 'simulation-off',
    selectedConfiguredZone || 'no-configured-zone',
    mapIncident?.id || 'no-incident',
    affectedRisk,
    simulation.effective_risk || 'LOW'
  ].join(':')

  async function handleLogout() {
    await signOut()
    navigate('/login', { replace: true })
  }

  async function updateSimulation(enabled, scenario = selectedScenario) {
    setSimulationSaving(true)
    setError('')
    try {
      const response = await apiFetch('/admin/simulation/state', { method: 'POST', body: JSON.stringify({ enabled, forced_risk: scenario.risk, scenario_name: scenario.name, escalation_enabled: false }) }, token)
      setSimulation(response.state)
      void loadAuditEvents(0)
      if (!enabled) {
        clearDemoAlert()
        setDemoRecipientPreview(null)
        setDemoLaunchResult(null)
        setOfflineDemoPreview(null)
        setOfflineDemoConfirmed(false)
        setOfflineDemoResult(null)
      }
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required to control simulation mode.' : 'Unable to update simulation mode.')
    } finally {
      setSimulationSaving(false)
    }
  }

  async function previewRecipients(riskOverride) {
    if (!affectedZoneId || selectedIncident) return
    const previewRisk = typeof riskOverride === 'string' ? riskOverride : affectedRisk
    setPreviewLoading(true)
    setError('')
    try {
      const result = await apiFetch('/admin/affected-zones/preview', {
        method: 'POST',
        body: JSON.stringify({
          zone_id: affectedZoneId,
          risk_level: previewRisk,
          message: affectedMessage,
          duration_minutes: Number(affectedDuration)
        })
      }, token)
      setRecipientPreview(result)
      setActivationConfirm(false)
      setActivationResult(null)
      setSendSms(false)
      void loadAuditEvents(0)
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required to preview recipients.' : 'Unable to generate the recipient preview.')
      setRecipientPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  function previewDecisionRecipients() {
    return previewRecipients(zoneIntelligence?.assessment?.overallRisk)
  }

  async function activateTargetedAlert() {
    if (!recipientPreview || !affectedZoneId || selectedIncident || simulation.enabled) return
    setActivationLoading(true)
    setError('')
    try {
      const result = await apiFetch('/admin/affected-zones/activate', {
        method: 'POST',
        body: JSON.stringify({ zone_id: affectedZoneId, risk_level: affectedRisk, message: affectedMessage, duration_minutes: Number(affectedDuration), send_sms: sendSms })
      }, token)
      setActivationResult(result)
      setActivationConfirm(false)
      refreshDashboard()
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required to activate targeted alerts.' : 'Unable to activate the targeted alert.')
      void loadAuditEvents(0)
    } finally {
      setActivationLoading(false)
    }
  }

  function selectConfiguredZone(value) {
    setSelectedConfiguredZone(value)
    if (value) setSelectedIncidentScenario('')
    setRecipientPreview(null)
    setSendSms(false)
    setActivationConfirm(false)
    setActivationResult(null)

    setDemoRecipientPreview(null)
    setDemoLaunchResult(null)
    setOfflineDemoPreview(null)
    setOfflineDemoConfirmed(false)
    setOfflineDemoResult(null)
    const zone = zones.find((feature) => String(feature?.properties?.zone_id || '') === value)
    setAffectedRisk(String(zone?.properties?.risk_level || 'HIGH').toUpperCase())
    setAffectedMessage(DEFAULT_AFFECTED_MESSAGE)
    if (value) void recordUiAuditEvent({ event_type: 'ZONE_SELECTED', zone_id: value })
  }

  function selectIncidentScenario(value) {
    setSelectedIncidentScenario(value)
    if (value) setSelectedConfiguredZone('')
    setRecipientPreview(null)
    setActivationConfirm(false)
    setActivationResult(null)
    setSendSms(false)
    setDemoRecipientPreview(null)
    setDemoLaunchResult(null)
    setOfflineDemoPreview(null)
    setOfflineDemoConfirmed(false)
    setOfflineDemoResult(null)
    const incident = getIncidentScenario(value)
    if (incident) {
      setAffectedRisk(incident.demo_risk)
      void recordUiAuditEvent({ event_type: 'INCIDENT_SELECTED', incident_id: incident.id })
    }
  }

  function previewDemoCitizens() {
    if (!simulation.enabled || !selectedIncident || !simulateCitizens) return
    const preview = previewSimulatedRecipients(selectedIncident, simulatedCitizenLocations)
    setDemoRecipientPreview(preview)
    setDemoLaunchResult(null)
    void recordUiAuditEvent({ event_type: 'DEMO_INCIDENT_LAUNCHED', incident_id: selectedIncident.id, simulated_count: preview.inside_count })
  }

  function launchDemoAlert() {
    if (!simulation.enabled || !selectedIncident || !demoRecipientPreview) return
    const alert = buildDemoAlert(selectedIncident, demoRecipientPreview)
    saveDemoAlert(alert)
    setDemoLaunchResult(alert)
    void recordUiAuditEvent({ event_type: 'DEMO_ALERT_GENERATED', incident_id: selectedIncident.id, simulated_count: demoRecipientPreview.inside_count })
  }

  const selectOfflineDemoArea = useCallback(async (area) => {
    if (!simulation.enabled || !['configured-zone', 'incident'].includes(area?.type) || !['HIGH', 'CRITICAL'].includes(String(area?.risk || '').toUpperCase())) return
    if (area.type === 'configured-zone') {
      setSelectedConfiguredZone(area.id)
      setSelectedIncidentScenario('')
    }
    setRecipientPreview(null)
    setActivationConfirm(false)
    setActivationResult(null)
    setDemoRecipientPreview(null)
    setDemoLaunchResult(null)
    setAffectedRisk(String(area.risk).toUpperCase())
    setOfflineDemoLoading(true)
    setOfflineDemoConfirmed(false)
    setOfflineDemoResult(null)
    setError('')
    try {
      const preview = await apiFetch('/admin/offline-demo-alerts/preview', {
        method: 'POST', body: JSON.stringify(area.type === 'incident' ? { incident_id: area.id } : { zone_id: area.id })
      }, token)
      setOfflineDemoPreview(preview)
    } catch (err) {
      setOfflineDemoPreview(null)
      setError(err?.status === 409 ? 'Enable Simulation Mode before selecting an offline demo area.' : 'Unable to calculate offline-demo recipients for this red zone.')
    } finally {
      setOfflineDemoLoading(false)
    }
  }, [simulation.enabled, token])

  async function sendOfflineDemoAlert() {
    if (!simulation.enabled || !offlineDemoPreview || !offlineDemoConfirmed) return
    const channels = [offlineDemoChannels.sms ? 'SMS_DEMO' : null, offlineDemoChannels.bluetooth ? 'BLUETOOTH_DEMO' : null].filter(Boolean)
    if (!channels.length) return
    setOfflineDemoLoading(true)
    setError('')
    try {
      const result = await apiFetch('/admin/offline-demo-alerts/send', {
        method: 'POST',
        body: JSON.stringify({ ...(offlineDemoPreview.area.incidentId ? { incident_id: offlineDemoPreview.area.incidentId } : { zone_id: offlineDemoPreview.area.zoneId }), channels, confirmed: true })
      }, token)
      setOfflineDemoResult(result)
      if (result.demoAlert) saveDemoAlert(result.demoAlert)
      if (result.auditEvent) setAuditEvents((current) => [result.auditEvent, ...current.filter((item) => item.eventId !== result.auditEvent.eventId)])
      else void loadAuditEvents(0)
    } catch (err) {
      setError(err?.status === 409 ? 'Simulation Mode is no longer active. No demo alert was generated.' : 'Unable to generate the offline alert demonstration.')
    } finally {
      setOfflineDemoLoading(false)
    }
  }

  const systemStates = Object.values(data.stats?.system || {})
  const systemSummary = !data.stats
    ? '—'
    : systemStates.length && systemStates.every((state) => ['operational', 'connected', 'jwt-enabled'].includes(String(state).toLowerCase()))
      ? 'Operational'
      : 'Warning'
  const cards = [
    { label: 'Active risk zones', value: data.stats?.risk_zones ?? '—', icon: AlertTriangle, tone: 'text-amber-100' },
    { label: 'Active alerts', value: data.stats?.active_alerts ?? '—', icon: Activity, tone: 'text-rose-100' },
    { label: 'Monitored users', value: data.stats?.active_locations ?? '—', icon: Users, tone: 'text-cyan-200' },
    { label: 'System status', value: systemSummary, icon: ShieldCheck, tone: systemSummary === 'Operational' ? 'text-emerald-200' : 'text-amber-100' }
  ]

  return (
    <main className="admin-shell px-3 py-4 sm:px-6 lg:px-8">
      <div className="admin-layout mx-auto max-w-[1600px]">
        <aside className="admin-sidebar" aria-label="Admin navigation">
          <div className="admin-sidebar-brand"><img src="/icons/landsense-logo.png" alt="" className="h-5 w-5 rounded-md object-contain" />LandSense</div>
          <nav>
            <a href="#admin-overview" aria-current="page">Overview</a>
            <a href="#admin-risk-zones">Risk zones</a>
            <a href="#admin-alerts">Alerts</a>
            <a href="#admin-users">Users</a>
            <a href="#incident-intelligence-map">Analytics</a>
            <a href="#admin-system">System</a>
          </nav>
        </aside>
        <div className="admin-content space-y-4">
        <header className="admin-page-header flex flex-col gap-4 border-b border-[#dfe5df] bg-white p-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <img src="/icons/landsense-logo.png" alt="LandSense" className="h-11 w-11 shrink-0 rounded-xl object-contain" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#1f5d42]">LandSense operations</p>
              <h1 className="text-xl font-bold tracking-tight">System Overview</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-300">Admin: {profile?.phone_masked || profile?.phone || profile?.uid || 'Authenticated operator'}</div>
            <button onClick={refreshDashboard} disabled={loading || zoneLoading} className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/20 bg-cyan-400/10 px-3 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading || zoneLoading ? 'animate-spin' : ''}`} /> Refresh</button>
            <button onClick={handleLogout} className="inline-flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-sm font-semibold text-slate-300 hover:bg-white/5"><LogOut className="h-4 w-4" /> Logout</button>
          </div>
        </header>

        {error ? <div className="rounded-2xl border border-rose-300/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}
        {zoneLoadError ? <div className="rounded-2xl border border-rose-300/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{zoneLoadError}</div> : null}
        {simulation.enabled ? <div className="rounded-2xl border border-amber-300/40 bg-amber-400/15 px-4 py-3 text-sm text-amber-50"><b>SIMULATION MODE ACTIVE</b><div className="mt-1">All displayed emergency conditions are simulated. External notifications are suppressed.</div></div> : null}

        <section id="admin-overview" className="admin-overview grid scroll-mt-4 grid-cols-2 border border-[#dfe5df] bg-white lg:grid-cols-4">
          {cards.map(({ label, value, icon: Icon, tone }) => <div key={label} className="admin-summary-item flex items-center gap-3 p-3"><Icon className={`h-4 w-4 ${tone}`} /><div><div className="text-lg font-bold leading-none">{value}</div><div className="mt-1 text-xs text-slate-500">{label}</div></div></div>)}
        </section>

        <AdminKodaguSimulation token={token} state={simulation} onStateChange={setSimulation} />


        <section id="admin-risk-zones" className="admin-risk-zones scroll-mt-4 border border-[#dfe5df] bg-white p-4">
          <div className="flex items-center gap-2"><MapPin className="h-5 w-5 text-cyan-200" /><h2 className="font-semibold">Configured alert zones and incident demos</h2></div>
          <p className="mt-1 text-sm text-slate-400">Only configured zones can use real recipient preview and activation. Incident scenarios remain isolated client-side demonstrations.</p>

          <div className="mt-4 rounded-2xl border border-cyan-300/15 bg-cyan-400/5 p-4">
            <h3 className="text-xs font-bold tracking-[0.18em] text-cyan-200">A. CONFIGURED ALERT ZONES</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="text-sm text-slate-300">Configured zone<select value={selectedConfiguredZone} onChange={(event) => selectConfiguredZone(event.target.value)} disabled={zoneLoading || Boolean(zoneLoadError) || !zones.length} className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white disabled:opacity-60">{zoneLoading ? <option value="">Loading configured zones…</option> : zoneLoadError ? <option value="">Unable to load configured zones</option> : !zones.length ? <option value="">No configured alert zones available</option> : <><option value="">Select configured zone</option>{zones.map((zone) => <option key={zone.properties?.zone_id} value={zone.properties?.zone_id}>{zone.properties?.name || zone.properties?.zone_id}</option>)}</>}</select></label>
              <label className="text-sm text-slate-300">Risk<select value={affectedRisk} onChange={(event) => setAffectedRisk(event.target.value)} disabled={!selectedConfiguredZone} className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white disabled:opacity-60">{RISK_ORDER.map((risk) => <option key={risk} value={risk}>{risk}</option>)}</select></label>
              <label className="text-sm text-slate-300">Duration (minutes)<input type="number" min="5" max="10080" value={affectedDuration} onChange={(event) => setAffectedDuration(event.target.value)} disabled={!selectedConfiguredZone} className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white disabled:opacity-60" /></label>
              <div className="flex items-end"><button type="button" disabled={!selectedConfiguredZone || previewLoading} onClick={previewRecipients} className="w-full rounded-xl bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">{previewLoading ? 'Preparing preview…' : 'Preview recipients'}</button></div>
            </div>
            <label style={{ display: 'none' }} className="mt-3 block text-sm text-slate-300">Message<textarea value={affectedMessage === DEFAULT_AFFECTED_MESSAGE ? '' : affectedMessage} onChange={(event) => setAffectedMessage(event.target.value)} disabled={!selectedConfiguredZone} maxLength="1000" rows="2" className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white disabled:opacity-60" /></label>
            {selectedConfiguredZone ? <div className="mt-3 rounded-xl border border-cyan-300/25 bg-cyan-400/10 p-4 text-sm text-cyan-50">
              <div className="flex flex-wrap items-center justify-between gap-2"><b>CONFIGURED RISK ZONE</b><RiskPill value={selectedConfiguredZoneGeometry?.properties?.risk_level} /></div>
              <p className="mt-2 text-base font-semibold">{selectedConfiguredZoneGeometry?.properties?.name || selectedConfiguredZone}</p>
              <p className="mt-1 text-slate-300">Duration: {affectedDuration} minutes</p>
              <p className={`mt-2 font-semibold ${selectedConfiguredZoneGeometry?.geometry ? 'text-emerald-200' : 'text-amber-200'}`}>{selectedConfiguredZoneGeometry?.geometry ? 'Configured zone geometry is displayed on the map.' : 'Selected zone geometry is unavailable.'}</p>
              <p className="mt-1 text-xs text-slate-400">Selection only — no alert has been activated.</p>
            </div> : <p className="mt-3 rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-slate-400">Select a configured zone to display its geometry on the map. No alert is active.</p>}
          </div>

          <div className="mt-4 rounded-2xl border border-orange-300/20 bg-orange-400/5 p-4">
            <h3 className="text-xs font-bold tracking-[0.18em] text-orange-200">B. RECENT / HISTORICAL INCIDENT DEMO SCENARIOS</h3>
            <label className="mt-3 block text-sm text-slate-300">Incident scenario<select value={selectedIncidentScenario} onChange={(event) => selectIncidentScenario(event.target.value)} className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white"><option value="">Select incident demo</option>{INCIDENT_SCENARIOS.map((incident) => <option key={incident.id} value={incident.id}>{incident.title} — {formatIncidentDate(incident.date)} — {incident.demo_risk}</option>)}</select></label>
            {selectedIncident ? <div className="mt-4 grid gap-4">
              <div className="rounded-xl border border-orange-300/25 bg-orange-400/10 p-4 text-sm text-orange-50">
                <div className="flex flex-wrap items-center justify-between gap-2"><b>{INCIDENT_SCENARIO_LABEL}</b><RiskPill value={selectedIncident.demo_risk} /></div>
                <h4 className="mt-3 text-lg font-bold">{selectedIncident.title}</h4>
                <p className="mt-1">{selectedIncident.location_name}, {selectedIncident.district}, {selectedIncident.state}</p>
                <p className="mt-1">{formatIncidentDate(selectedIncident.date)} · Approximate incident location</p>
                <p className="mt-3 text-orange-100">{selectedIncident.short_description}</p>
                <div className="mt-3 flex flex-wrap gap-2">{impactLines(selectedIncident).map((line) => <span key={line} className="rounded-full border border-white/15 px-2.5 py-1 text-xs">{line}</span>)}</div>
                <p className="mt-3">Affected radius: {(selectedIncident.affected_radius_meters / 1000).toFixed(1)} km · demo visualization</p>
                {selectedIncident.verification_status === 'source_review_required' ? <p className="mt-3 rounded-lg border border-amber-200/30 bg-amber-200/10 px-3 py-2 font-bold text-amber-100">SOURCE REVIEW REQUIRED · DEMO ONLY</p> : <p className="mt-3 text-emerald-200">Published incident source verified.</p>}
                <a className="mt-2 inline-block text-cyan-200 underline" href={selectedIncident.source_url} target="_blank" rel="noreferrer">Source: {selectedIncident.source_label}</a>
              </div>
              <div style={{ display: 'none' }} className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm">
                <h4 className="font-bold">INCIDENT OVERVIEW</h4>
                <p className="mt-2 font-bold text-amber-200">DEMO ONLY — TARGETING DISABLED</p>
                <label className="mt-4 flex items-start gap-3"><input type="checkbox" checked={simulateCitizens} onChange={(event) => { setSimulateCitizens(event.target.checked); setDemoRecipientPreview(null); setDemoLaunchResult(null) }} className="mt-1" /><span><b>Simulate citizen inside affected area</b><span style={{ visibility: 'hidden' }} className="block text-xs text-slate-400">Creates client-only demonstration markers. No GPS, Neon, location events, alerts, or recipients are modified.</span></span></label>
                {simulateCitizens ? <div className="mt-3 grid grid-cols-2 gap-3"><label>Inside<input type="number" min="1" max="50" value={insideCitizenCount} onChange={(event) => { setInsideCitizenCount(event.target.value); setDemoRecipientPreview(null) }} className="mt-1 w-full rounded-lg border border-white/10 bg-[#091521] px-2 py-1" /></label><label>Outside<input type="number" min="0" max="50" value={outsideCitizenCount} onChange={(event) => { setOutsideCitizenCount(event.target.value); setDemoRecipientPreview(null) }} className="mt-1 w-full rounded-lg border border-white/10 bg-[#091521] px-2 py-1" /></label></div> : null}
                {!simulation.enabled ? <p className="mt-3 text-amber-200">Enable Simulation Mode to preview or launch this demo.</p> : null}
                <button type="button" onClick={previewDemoCitizens} disabled={!simulation.enabled || !simulateCitizens} className="mt-4 w-full rounded-lg border border-orange-300/30 bg-orange-400/15 px-3 py-2 font-semibold disabled:opacity-50">Preview simulated citizens</button>
                {demoRecipientPreview ? <div className="mt-3 rounded-lg bg-white/5 p-3"><p>Simulated citizens: {demoRecipientPreview.total_count}</p><p>Inside affected area: {demoRecipientPreview.inside_count}</p><p>Outside affected area: {demoRecipientPreview.outside_count}</p><button type="button" onClick={launchDemoAlert} className="mt-3 w-full rounded-lg bg-orange-400 px-3 py-2 font-bold text-slate-950">Launch Demo Alert</button></div> : null}
                {demoRecipientPreview ? <div className="mt-3 rounded-lg border border-violet-300/25 bg-violet-400/10 p-3"><b>SIMULATED NOTIFICATION</b><p className="mt-1">Recipients: {demoRecipientPreview.inside_count} simulated citizens</p><pre className="mt-3 whitespace-pre-wrap rounded-lg bg-black/25 p-3 text-xs text-violet-50">{buildSimulatedSms(selectedIncident)}</pre></div> : null}
                {demoLaunchResult ? <div className="mt-3 rounded-lg border border-emerald-300/25 bg-emerald-400/10 p-3 text-emerald-100"><b>SIMULATED ALERT</b><p className="mt-1">Visible in the citizen demo inbox.</p><p>SIMULATED SMS — NOT SENT</p></div> : null}
              </div>
            </div> : null}
          </div>
          {selectedConfiguredZone ? <div className="mt-4"><IntelligenceCard intelligence={zoneIntelligence} loading={intelligenceLoading} error={intelligenceError} simulatedCitizens={displayedSimulatedCitizens} simulationEnabled={simulation.enabled} onPreview={previewRecipients} previewLoading={previewLoading} realRecipientCount={realRecipientCount} /></div> : null}
          {recipientPreview ? <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-400/5 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-semibold">Recipient preview</h3><p className="mt-1 text-sm text-cyan-100">Users inside zone: {recipientPreview.recipient_count} of {recipientPreview.total_registered_users} registered users</p><p className="mt-1 text-sm font-semibold text-violet-200">Eligible SMS recipients: {recipientPreview.sms_eligible_count ?? 0}</p></div><span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2.5 py-1 text-xs font-bold text-amber-100">PREVIEW ONLY · ADMIN SIMULATION</span></div><p className="mt-2 text-xs text-slate-400">{recipientPreview.affected_zone?.name} · starts {displayTime(recipientPreview.affected_zone?.start_time)} · expires {displayTime(recipientPreview.affected_zone?.expires_at)}</p><div className="mt-3 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b border-white/10 text-slate-400"><tr><th className="px-2 py-2">User</th><th className="px-2 py-2">Location</th><th className="px-2 py-2">Last updated</th><th className="px-2 py-2">Risk</th></tr></thead><tbody>{recipientPreview.recipients?.map((recipient) => <tr key={recipient.user_id} className="border-b border-white/5"><td className="px-2 py-2">{recipient.phone_masked || recipient.user_id}</td><td className="px-2 py-2 font-mono text-xs">{Number(recipient.latitude).toFixed(5)}, {Number(recipient.longitude).toFixed(5)}</td><td className="px-2 py-2 text-slate-400">{displayTime(recipient.last_updated)}</td><td className="px-2 py-2">{recipient.current_risk ? <RiskPill value={recipient.current_risk} /> : '—'}</td></tr>)}{!recipientPreview.recipients?.length ? <tr><td colSpan="4" className="px-2 py-4 text-center text-slate-400">No registered users are currently inside this zone.</td></tr> : null}</tbody></table></div><p className="mt-3 text-sm text-amber-100">Preview only — no alert has been sent.</p></div> : null}
          {recipientPreview && !activationResult ? <div className="mt-3 rounded-xl border border-amber-300/30 bg-amber-400/10 p-3"><label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={sendSms} onChange={(event) => setSendSms(event.target.checked)} disabled={recipientPreview.simulation_mode || simulation.enabled} className="mt-1 h-4 w-4" /><span><b>Send SMS to eligible users</b><span className="mt-1 block text-xs text-amber-50">In-app alert will always be created. SMS is optional and only sent to eligible users inside the zone.</span></span></label>{simulation.enabled ? <p className="mt-2 text-sm font-semibold text-amber-200">SIMULATION MODE — real configured-zone activation is disabled. Turn simulation off to activate.</p> : null}{sendSms && !recipientPreview.sms_configuration?.configured ? <p className="mt-2 text-xs text-rose-200">Twilio SMS is not configured. In-app alerts will still be created.</p> : null}{sendSms && (recipientPreview.sms_eligible_count ?? 0) > (recipientPreview.sms_max_recipients ?? 25) ? <p className="mt-2 text-xs text-rose-200">Eligible recipients exceed the SMS batch limit of {recipientPreview.sms_max_recipients}. SMS will be refused without truncation.</p> : null}{activationConfirm ? <><p className="mt-3 text-sm font-semibold text-amber-100">{sendSms ? `Send SMS to ${recipientPreview.sms_eligible_count ?? 0} eligible users?` : `Create in-app alerts for ${recipientPreview.recipient_count} users?`}</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => setActivationConfirm(false)} disabled={activationLoading} className="rounded-lg border border-white/15 px-3 py-2 text-sm">Cancel</button><button type="button" onClick={activateTargetedAlert} disabled={activationLoading || simulation.enabled} className="rounded-lg bg-amber-300 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">{activationLoading ? 'Activating…' : sendSms ? 'Send SMS' : 'Activate alert'}</button></div></> : <button type="button" disabled={!recipientPreview.recipient_count || simulation.enabled} onClick={() => setActivationConfirm(true)} className="mt-3 rounded-xl bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Activate targeted alert</button>}</div> : null}
          {activationResult ? <div className={`mt-3 rounded-xl border px-3 py-3 text-sm ${activationResult.sms_failed || activationResult.status === 'sms_batch_limit_exceeded' ? 'border-rose-300/25 bg-rose-400/10 text-rose-100' : 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100'}`}><p>In-app alerts created: {activationResult.in_app_created_count ?? 0} of {activationResult.recipient_count} recipients.</p><p className="mt-1">SMS eligible: {activationResult.sms_eligible_count}; attempted: {activationResult.sms_attempted}; sent: {activationResult.sms_sent}; failed: {activationResult.sms_failed}; suppressed: {activationResult.sms_suppressed}.</p>{activationResult.status === 'simulation_sms_suppressed' ? <p className="mt-1 font-semibold">Simulation mode — SMS suppressed.</p> : null}{activationResult.status === 'sms_provider_unavailable' ? <p className="mt-1 font-semibold">Twilio is not configured. In-app delivery succeeded.</p> : null}{activationResult.status === 'sms_batch_limit_exceeded' ? <p className="mt-1 font-semibold">SMS batch limit exceeded. No SMS was attempted; in-app delivery succeeded.</p> : null}{activationResult.deduplicated_count ? <p className="mt-1">{activationResult.deduplicated_count} duplicate recipient(s) were suppressed.</p> : null}</div> : null}
        </section>

        <AdminHttpsmsExport key={`${simulation.enabled}:${selectedConfiguredZone}:${selectedIncidentScenario}`} zoneId={selectedIncidentScenario ? '' : selectedConfiguredZone} simulationEnabled={simulation.enabled} token={token} />
        <AdminAuditTimeline events={auditEvents} loading={auditLoading} error={auditError} hasMore={auditHasMore} loadingMore={auditLoadingMore} onRetry={() => loadAuditEvents(0)} onLoadMore={() => loadAuditEvents(auditEvents.length)} />

        <section id="incident-intelligence-map" className="admin-map-section grid scroll-mt-4 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,.65fr)]">
          <div className="overflow-hidden rounded-3xl border border-white/8 bg-[#0c1724] p-4">
            <div className="mb-3 flex items-center justify-between"><div><h2 className="font-semibold">Incident intelligence map</h2><p className="text-xs text-slate-400">{simulation.is_simulation ? (simulation.synthetic_zone?.geometry ? 'Kodagu simulation overlays are displayed on this existing map; normal incident and inventory layers remain unchanged.' : 'Simulation map geometry unavailable. No verified project geometry exists for this location. Safer route unavailable. No verified route geometry exists.') : activeMapIncident ? 'Simulation is active. The map is centered on the selected demo incident and circular affected area.' : contextualMapIncident ? 'The configured zone, matched recent incident, affected radius, and real population are shown together.' : simulation.enabled && selectedIncident ? 'Selected incident location is unavailable.' : selectedIncident ? 'Enable Simulation Mode to display the selected incident on the map.' : selectedConfiguredZoneGeometry?.geometry ? 'The selected configured zone is highlighted and fitted in view. Selection does not activate an alert.' : selectedConfiguredZone ? 'Selected zone geometry is unavailable.' : 'Select a configured zone or enable simulation and choose an incident to focus the map.'}</p></div><MapPin className="h-5 w-5 text-cyan-200" /></div>
            <div className="h-[390px] overflow-hidden rounded-2xl"><MapView key={adminMapKey} zones={zones} simulatedLocation={activeMapIncident ? null : simulationLocation} simulatedCitizens={displayedSimulatedCitizens} syntheticZone={simulation.synthetic_zone} simulationRoute={simulation.route} showSimulationLayers={String(profile?.role || '').toLowerCase() === 'admin' && simulation.enabled && simulation.is_simulation} affectedUserLocations={realAffectedUsers} incidentLocation={mapIncidentLocation} incidentRadiusMeters={mapIncident?.affected_radius_meters || 0} incidentMode={incidentDemoMode} mapContext={mapContext} recipientLocations={recipientPreview?.recipients || []} selectedZone={selectedConfiguredZoneGeometry} selectedZoneRisk={selectedConfiguredZoneGeometry?.properties?.risk_level || ''} selectedZoneDuration={affectedDuration} risk={mapIncident?.demo_risk || (simulation.enabled ? simulation.effective_risk : (data.events[0]?.final_risk || 'SAFE'))} simulation={simulation.enabled} landslideRecords={data.landslides} onRiskAreaSelect={selectOfflineDemoArea} /></div>
            {simulation.enabled && !offlineDemoPreview ? <p className="mt-3 rounded-xl border border-red-300/20 bg-red-400/5 px-3 py-2 text-sm text-red-100">Click a configured red HIGH / CRITICAL zone or the selected incident's circular affected area to calculate affected registered users and open the offline alert demonstration.</p> : null}
            <AdminOfflineAlertDemo preview={offlineDemoPreview} channels={offlineDemoChannels} onChannelChange={(channel, checked) => { setOfflineDemoChannels((current) => ({ ...current, [channel]: checked })); setOfflineDemoResult(null) }} confirmation={offlineDemoConfirmed} onConfirmationChange={setOfflineDemoConfirmed} onSend={sendOfflineDemoAlert} loading={offlineDemoLoading} result={offlineDemoResult} />
          </div>
          <div id="admin-system" className="admin-operations-panel admin-alert-stream border border-[#dfe5df] bg-white p-4">
            <div className="section-kicker">Alert stream</div>
            <h2 className="mt-1 font-semibold">Active alerts</h2>
            <div className="mt-3 divide-y divide-[#e5e9e6]">{data.alerts.length ? data.alerts.slice(0, 4).map((alert) => <div key={alert.id} className="flex items-center justify-between gap-3 py-3"><div><RiskPill value={alert.risk_level} /><p className="mt-1 text-xs text-slate-500">{displayTime(alert.timestamp)}</p></div><span className="text-xs text-slate-600">{alert.status || 'recorded'}</span></div>) : <p className="py-3 text-sm text-slate-500">No active alerts.</p>}</div>
            <h2 className="mt-5 border-t border-[#dfe5df] pt-4 font-semibold">Risk overview</h2><p className="mt-1 text-xs text-slate-500">Persisted location events</p>
            <div className="mt-5 space-y-3">{RISK_ORDER.map((risk) => <div key={risk} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.03] px-3 py-3"><RiskPill value={risk} /><span className="text-xl font-bold">{data.stats?.risk_summary?.[risk] ?? 0}</span></div>)}</div>
            <div className="mt-5 border-t border-white/8 pt-4"><h3 className="text-sm font-semibold">Landslide Inventory</h3><p className="mt-2 text-2xl font-bold text-violet-200">{data.stats?.landslide_inventory?.records ?? 0}</p><p className="mt-1 text-xs text-slate-400">{data.stats?.landslide_inventory?.source || 'Field-validated landslide inventory'} · historical dataset</p><p className="mt-1 text-xs text-slate-500">Year range: {data.stats?.landslide_inventory?.date_range?.from ?? 'unknown'}–{data.stats?.landslide_inventory?.date_range?.to ?? 'unknown'}. Context only; does not trigger alerts.</p></div>
            <div className="mt-5 border-t border-white/8 pt-4"><h3 className="text-sm font-semibold">System status</h3>{Object.entries(data.stats?.system || {}).map(([name, status]) => <div className="mt-3 flex items-center justify-between text-sm" key={name}><span className="capitalize text-slate-400">{name}</span><span style={{ visibility: ['operational', 'connected', 'jwt enabled'].includes(String(status).replace('-', ' ')) ? 'hidden' : undefined }} className="text-emerald-200">{String(status).replace('-', ' ')}</span></div>)}</div>
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-2">
          <div id="admin-alerts" className="scroll-mt-4 rounded-lg border border-white/8 bg-[#0c1724] p-5"><h2 className="font-semibold">Recent alerts</h2><div className="mt-4 divide-y divide-[#e5e9e6]">{data.alerts.length ? data.alerts.map((alert) => <div key={alert.id} className="flex items-center justify-between gap-3 py-3"><div><RiskPill value={alert.risk_level} /><p className="mt-2 text-xs text-slate-400">{displayTime(alert.timestamp)}</p></div><span className="text-right text-xs text-slate-300">{alert.status || 'recorded'}</span></div>) : <p className="p-4 text-sm text-slate-400">No active alerts.</p>}</div></div>
          <div className="overflow-hidden rounded-lg border border-[#dfe5df] bg-white"><div className="border-b border-[#dfe5df] px-4 py-3"><h2 className="font-semibold">Recent risk assessments</h2></div><div className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="bg-[#f8faf8] text-xs text-slate-500"><tr><th className="px-4 py-2.5">Risk</th><th className="px-4 py-2.5">Date and time</th><th className="px-4 py-2.5">Rainfall</th><th className="px-4 py-2.5">Status</th></tr></thead><tbody>{data.events.length ? data.events.slice(0, 6).map((event) => <tr key={event.id} className="border-t border-[#e5e9e6]"><td className="px-4 py-3"><RiskPill value={event.final_risk} /></td><td className="whitespace-nowrap px-4 py-3 text-slate-600">{displayTime(event.timestamp_utc)}</td><td className="whitespace-nowrap px-4 py-3 text-slate-600">{Number(event.rainfall_mm || 0).toFixed(1)} mm</td><td className="px-4 py-3 text-slate-700">{event.geofence_event || event.active_zone_id || 'Location update'}</td></tr>) : <tr><td colSpan="4" className="px-4 py-6 text-center text-slate-500">No location events have been recorded.</td></tr>}</tbody></table></div></div>
        </section>

        <section id="admin-users" className="scroll-mt-4 rounded-lg border border-white/8 bg-[#0c1724] p-5"><div className="flex items-end justify-between gap-4"><div><h2 className="font-semibold">User monitoring</h2><p className="mt-1 text-xs text-slate-400">Safe identity fields only; data is paginated by the API.</p></div><Link to="/" className="text-sm text-cyan-200 hover:text-cyan-100">Citizen view</Link></div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b border-white/10 text-slate-400"><tr><th className="px-3 py-3">User ID</th><th className="px-3 py-3">Phone</th><th className="px-3 py-3">Role</th><th className="px-3 py-3">Last updated</th><th className="px-3 py-3">Status</th></tr></thead><tbody>{data.users.map((user) => <tr key={user.user_id} className="border-b border-white/5"><td className="px-3 py-3 font-mono text-xs">{user.user_id}</td><td className="px-3 py-3">{user.phone_masked}</td><td className="px-3 py-3">{user.role}</td><td className="px-3 py-3 text-slate-400">{displayTime(user.last_updated)}</td><td className="px-3 py-3 text-slate-300">{user.status}</td></tr>)}{!loading && !data.users.length ? <tr><td colSpan="5" className="px-3 py-6 text-center text-slate-400">No users available.</td></tr> : null}</tbody></table></div></section>
        </div>
      </div>
    </main>
  )
}
