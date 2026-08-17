import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, LogOut, MapPin, Power, RefreshCw, ShieldCheck, Users } from 'lucide-react'
import MapView from '../shared/MapView'
import { apiFetch } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { INCIDENT_SCENARIO_LABEL, INCIDENT_SCENARIOS, getIncidentScenario } from '../data/incidentScenarios'
import { buildDemoAlert, buildSimulatedSms, clearDemoAlert, formatIncidentDate, generateSimulatedCitizens, impactLines, previewSimulatedRecipients, saveDemoAlert } from '../services/incidentDemo'

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
        apiFetch('/landslides?limit=2000', {}, token)
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
  }, [loadConfiguredZones, loadDashboard])

  useEffect(() => {
    void loadDashboard()
    void loadConfiguredZones()
  }, [loadConfiguredZones, loadDashboard])

  const selectedIncident = useMemo(() => getIncidentScenario(selectedIncidentScenario), [selectedIncidentScenario])
  const affectedZoneId = selectedConfiguredZone

  const simulationLocation = simulation.enabled && simulation.danger_latitude != null && simulation.danger_longitude != null
      ? { lat: simulation.danger_latitude, lng: simulation.danger_longitude, label: simulation.danger_zone_name || simulation.scenario_name }
      : null

  const simulatedCitizenLocations = useMemo(
    () => simulateCitizens && selectedIncident ? generateSimulatedCitizens(selectedIncident, insideCitizenCount, outsideCitizenCount) : [],
    [simulateCitizens, selectedIncident, insideCitizenCount, outsideCitizenCount]
  )

  const selectedConfiguredZoneGeometry = useMemo(
    () => zones.find((zone) => String(zone?.properties?.zone_id || '') === affectedZoneId) || null,
    [zones, affectedZoneId]
  )

  const activeMapIncident = useMemo(() => {
    if (!simulation.enabled || !selectedIncident) return null
    const latitude = Number(selectedIncident.latitude)
    const longitude = Number(selectedIncident.longitude)
    return Number.isFinite(latitude) && Number.isFinite(longitude) ? selectedIncident : null
  }, [selectedIncident, simulation.enabled])

  const adminMapKey = [
    simulation.enabled ? 'simulation-on' : 'simulation-off',
    selectedConfiguredZone || 'no-configured-zone',
    activeMapIncident?.id || 'no-incident',
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
      if (!enabled) {
        clearDemoAlert()
        setDemoRecipientPreview(null)
        setDemoLaunchResult(null)
      }
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required to control simulation mode.' : 'Unable to update simulation mode.')
    } finally {
      setSimulationSaving(false)
    }
  }

  async function previewRecipients() {
    if (!affectedZoneId || selectedIncident) return
    setPreviewLoading(true)
    setError('')
    try {
      const result = await apiFetch('/admin/affected-zones/preview', {
        method: 'POST',
        body: JSON.stringify({
          zone_id: affectedZoneId,
          risk_level: affectedRisk,
          message: affectedMessage,
          duration_minutes: Number(affectedDuration)
        })
      }, token)
      setRecipientPreview(result)
      setActivationConfirm(false)
      setActivationResult(null)
      setSendSms(false)
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required to preview recipients.' : 'Unable to generate the recipient preview.')
      setRecipientPreview(null)
    } finally {
      setPreviewLoading(false)
    }
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
    const zone = zones.find((feature) => String(feature?.properties?.zone_id || '') === value)
    setAffectedRisk(String(zone?.properties?.risk_level || 'HIGH').toUpperCase())
    setAffectedMessage(DEFAULT_AFFECTED_MESSAGE)
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
    const incident = getIncidentScenario(value)
    if (incident) setAffectedRisk(incident.demo_risk)
  }

  function previewDemoCitizens() {
    if (!simulation.enabled || !selectedIncident || !simulateCitizens) return
    setDemoRecipientPreview(previewSimulatedRecipients(selectedIncident, simulatedCitizenLocations))
    setDemoLaunchResult(null)
  }

  function launchDemoAlert() {
    if (!simulation.enabled || !selectedIncident || !demoRecipientPreview) return
    const alert = buildDemoAlert(selectedIncident, demoRecipientPreview)
    saveDemoAlert(alert)
    setDemoLaunchResult(alert)
  }

  const cards = [
    { label: 'Total users', value: data.stats?.total_users ?? '—', icon: Users, tone: 'text-cyan-200' },
    { label: 'Active locations', value: data.stats?.active_locations ?? '—', icon: MapPin, tone: 'text-emerald-200' },
    { label: 'Risk zones', value: data.stats?.risk_zones ?? '—', icon: AlertTriangle, tone: 'text-amber-100' },
    { label: 'Recorded alerts', value: data.stats?.active_alerts ?? '—', icon: Activity, tone: 'text-rose-100' }
  ]

  return (
    <main className="min-h-screen bg-[#07101a] px-4 py-5 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="flex flex-col gap-4 rounded-3xl border border-cyan-300/10 bg-[#0c1724] p-5 shadow-2xl shadow-black/20 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-400/15 text-cyan-200"><ShieldCheck /></div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200">LandSense command centre</p>
              <h1 className="text-2xl font-bold tracking-tight">Admin Dashboard</h1>
              <p className="mt-1 text-sm text-slate-400">Read-only operational view of users, risk zones, alerts and location events.</p>
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

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {cards.map(({ label, value, icon: Icon, tone }) => <div key={label} className="rounded-2xl border border-white/8 bg-[#0c1724] p-4"><Icon className={`h-5 w-5 ${tone}`} /><div className="mt-4 text-3xl font-bold">{value}</div><div className="mt-1 text-sm text-slate-400">{label}</div></div>)}
        </section>

        <section className="rounded-3xl border border-amber-300/20 bg-[#151724] p-5"><div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><div className="flex items-center gap-2"><Power className="h-5 w-5 text-amber-200" /><h2 className="font-semibold">Simulation mode</h2><span className={`rounded-full px-2 py-1 text-xs font-bold ${simulation.enabled ? 'bg-amber-300 text-slate-950' : 'bg-white/10 text-slate-300'}`}>{simulation.enabled ? 'ON' : 'OFF'}</span></div><p className="mt-1 text-sm text-slate-400">Presentation-only state; no live events or SMS are created.</p></div><div className="flex gap-2"><button type="button" disabled={simulationSaving || simulation.enabled} onClick={() => updateSimulation(true)} className="rounded-xl bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Enable</button><button type="button" disabled={simulationSaving || !simulation.enabled} onClick={() => updateSimulation(false)} className="rounded-xl border border-white/15 px-4 py-2 text-sm font-semibold disabled:opacity-50">Disable / Reset</button></div></div><div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{SIMULATION_SCENARIOS.map((scenario) => <button key={scenario.name} type="button" disabled={simulationSaving} onClick={() => { setSelectedScenario(scenario); if (simulation.enabled) void updateSimulation(true, scenario) }} className={`rounded-xl border p-3 text-left ${selectedScenario.name === scenario.name ? 'border-amber-300/50 bg-amber-400/10' : 'border-white/10 bg-white/[0.03]'}`}><RiskPill value={scenario.risk} /><div className="mt-2 text-sm font-semibold">{scenario.name}</div></button>)}</div><div className="mt-4 grid gap-2 text-sm sm:grid-cols-3"><div><span className="text-slate-400">Simulated risk:</span> <RiskPill value={simulation.effective_risk} /></div><div><span className="text-slate-400">Simulated location:</span> {simulation.danger_zone_name || 'Demonstration zone'}</div><div><span className="text-slate-400">Updated:</span> {displayTime(simulation.enabled_at_utc)}</div></div></section>

        <section className="rounded-3xl border border-cyan-300/20 bg-[#0c1724] p-5">
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
            <label className="mt-3 block text-sm text-slate-300">Message<textarea value={affectedMessage} onChange={(event) => setAffectedMessage(event.target.value)} disabled={!selectedConfiguredZone} maxLength="1000" rows="2" className="mt-1 block w-full rounded-xl border border-white/10 bg-[#091521] px-3 py-2 text-white disabled:opacity-60" /></label>
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
            {selectedIncident ? <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_.85fr]">
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
              <div className="rounded-xl border border-white/10 bg-black/20 p-4 text-sm">
                <h4 className="font-bold">INCIDENT OVERVIEW</h4>
                <p className="mt-2 font-bold text-amber-200">DEMO ONLY — TARGETING DISABLED</p>
                <label className="mt-4 flex items-start gap-3"><input type="checkbox" checked={simulateCitizens} onChange={(event) => { setSimulateCitizens(event.target.checked); setDemoRecipientPreview(null); setDemoLaunchResult(null) }} className="mt-1" /><span><b>Simulate citizen inside affected area</b><span className="block text-xs text-slate-400">Creates client-only demonstration markers. No GPS, Neon, location events, alerts, or recipients are modified.</span></span></label>
                {simulateCitizens ? <div className="mt-3 grid grid-cols-2 gap-3"><label>Inside<input type="number" min="1" max="50" value={insideCitizenCount} onChange={(event) => { setInsideCitizenCount(event.target.value); setDemoRecipientPreview(null) }} className="mt-1 w-full rounded-lg border border-white/10 bg-[#091521] px-2 py-1" /></label><label>Outside<input type="number" min="0" max="50" value={outsideCitizenCount} onChange={(event) => { setOutsideCitizenCount(event.target.value); setDemoRecipientPreview(null) }} className="mt-1 w-full rounded-lg border border-white/10 bg-[#091521] px-2 py-1" /></label></div> : null}
                {!simulation.enabled ? <p className="mt-3 text-amber-200">Enable Simulation Mode to preview or launch this demo.</p> : null}
                <button type="button" onClick={previewDemoCitizens} disabled={!simulation.enabled || !simulateCitizens} className="mt-4 w-full rounded-lg border border-orange-300/30 bg-orange-400/15 px-3 py-2 font-semibold disabled:opacity-50">Preview simulated citizens</button>
                {demoRecipientPreview ? <div className="mt-3 rounded-lg bg-white/5 p-3"><p>Simulated citizens: {demoRecipientPreview.total_count}</p><p>Inside affected area: {demoRecipientPreview.inside_count}</p><p>Outside affected area: {demoRecipientPreview.outside_count}</p><button type="button" onClick={launchDemoAlert} className="mt-3 w-full rounded-lg bg-orange-400 px-3 py-2 font-bold text-slate-950">Launch Demo Alert</button></div> : null}
                {demoRecipientPreview ? <div className="mt-3 rounded-lg border border-violet-300/25 bg-violet-400/10 p-3"><b>SIMULATED NOTIFICATION</b><p className="mt-1">Recipients: {demoRecipientPreview.inside_count} simulated citizens</p><pre className="mt-3 whitespace-pre-wrap rounded-lg bg-black/25 p-3 text-xs text-violet-50">{buildSimulatedSms(selectedIncident)}</pre></div> : null}
                {demoLaunchResult ? <div className="mt-3 rounded-lg border border-emerald-300/25 bg-emerald-400/10 p-3 text-emerald-100"><b>SIMULATED ALERT</b><p className="mt-1">Visible in the citizen demo inbox.</p><p>SIMULATED SMS — NOT SENT</p></div> : null}
              </div>
            </div> : null}
          </div>
          {recipientPreview ? <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-400/5 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-semibold">Recipient preview</h3><p className="mt-1 text-sm text-cyan-100">Users inside zone: {recipientPreview.recipient_count} of {recipientPreview.total_registered_users} registered users</p><p className="mt-1 text-sm font-semibold text-violet-200">Eligible SMS recipients: {recipientPreview.sms_eligible_count ?? 0}</p></div><span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2.5 py-1 text-xs font-bold text-amber-100">PREVIEW ONLY · ADMIN SIMULATION</span></div><p className="mt-2 text-xs text-slate-400">{recipientPreview.affected_zone?.name} · starts {displayTime(recipientPreview.affected_zone?.start_time)} · expires {displayTime(recipientPreview.affected_zone?.expires_at)}</p><div className="mt-3 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b border-white/10 text-slate-400"><tr><th className="px-2 py-2">User</th><th className="px-2 py-2">Location</th><th className="px-2 py-2">Last updated</th><th className="px-2 py-2">Risk</th></tr></thead><tbody>{recipientPreview.recipients?.map((recipient) => <tr key={recipient.user_id} className="border-b border-white/5"><td className="px-2 py-2">{recipient.phone_masked || recipient.user_id}</td><td className="px-2 py-2 font-mono text-xs">{Number(recipient.latitude).toFixed(5)}, {Number(recipient.longitude).toFixed(5)}</td><td className="px-2 py-2 text-slate-400">{displayTime(recipient.last_updated)}</td><td className="px-2 py-2">{recipient.current_risk ? <RiskPill value={recipient.current_risk} /> : '—'}</td></tr>)}{!recipientPreview.recipients?.length ? <tr><td colSpan="4" className="px-2 py-4 text-center text-slate-400">No registered users are currently inside this zone.</td></tr> : null}</tbody></table></div><p className="mt-3 text-sm text-amber-100">Preview only — no alert has been sent.</p></div> : null}
          {recipientPreview && !activationResult ? <div className="mt-3 rounded-xl border border-amber-300/30 bg-amber-400/10 p-3"><label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={sendSms} onChange={(event) => setSendSms(event.target.checked)} disabled={recipientPreview.simulation_mode || simulation.enabled} className="mt-1 h-4 w-4" /><span><b>Send SMS to eligible users</b><span className="mt-1 block text-xs text-amber-50">In-app alert will always be created. SMS is optional and only sent to eligible users inside the zone.</span></span></label>{simulation.enabled ? <p className="mt-2 text-sm font-semibold text-amber-200">SIMULATION MODE — real configured-zone activation is disabled. Turn simulation off to activate.</p> : null}{sendSms && !recipientPreview.sms_configuration?.configured ? <p className="mt-2 text-xs text-rose-200">Twilio SMS is not configured. In-app alerts will still be created.</p> : null}{sendSms && (recipientPreview.sms_eligible_count ?? 0) > (recipientPreview.sms_max_recipients ?? 25) ? <p className="mt-2 text-xs text-rose-200">Eligible recipients exceed the SMS batch limit of {recipientPreview.sms_max_recipients}. SMS will be refused without truncation.</p> : null}{activationConfirm ? <><p className="mt-3 text-sm font-semibold text-amber-100">{sendSms ? `Send SMS to ${recipientPreview.sms_eligible_count ?? 0} eligible users?` : `Create in-app alerts for ${recipientPreview.recipient_count} users?`}</p><div className="mt-3 flex gap-2"><button type="button" onClick={() => setActivationConfirm(false)} disabled={activationLoading} className="rounded-lg border border-white/15 px-3 py-2 text-sm">Cancel</button><button type="button" onClick={activateTargetedAlert} disabled={activationLoading || simulation.enabled} className="rounded-lg bg-amber-300 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">{activationLoading ? 'Activating…' : sendSms ? 'Send SMS' : 'Activate alert'}</button></div></> : <button type="button" disabled={!recipientPreview.recipient_count || simulation.enabled} onClick={() => setActivationConfirm(true)} className="mt-3 rounded-xl bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Activate targeted alert</button>}</div> : null}
          {activationResult ? <div className={`mt-3 rounded-xl border px-3 py-3 text-sm ${activationResult.sms_failed || activationResult.status === 'sms_batch_limit_exceeded' ? 'border-rose-300/25 bg-rose-400/10 text-rose-100' : 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100'}`}><p>In-app alerts created: {activationResult.in_app_created_count ?? 0} of {activationResult.recipient_count} recipients.</p><p className="mt-1">SMS eligible: {activationResult.sms_eligible_count}; attempted: {activationResult.sms_attempted}; sent: {activationResult.sms_sent}; failed: {activationResult.sms_failed}; suppressed: {activationResult.sms_suppressed}.</p>{activationResult.status === 'simulation_sms_suppressed' ? <p className="mt-1 font-semibold">Simulation mode — SMS suppressed.</p> : null}{activationResult.status === 'sms_provider_unavailable' ? <p className="mt-1 font-semibold">Twilio is not configured. In-app delivery succeeded.</p> : null}{activationResult.status === 'sms_batch_limit_exceeded' ? <p className="mt-1 font-semibold">SMS batch limit exceeded. No SMS was attempted; in-app delivery succeeded.</p> : null}{activationResult.deduplicated_count ? <p className="mt-1">{activationResult.deduplicated_count} duplicate recipient(s) were suppressed.</p> : null}</div> : null}
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,.8fr)]">
          <div className="overflow-hidden rounded-3xl border border-white/8 bg-[#0c1724] p-4">
            <div className="mb-3 flex items-center justify-between"><div><h2 className="font-semibold">Risk map</h2><p className="text-xs text-slate-400">{activeMapIncident ? 'Simulation is active. The map is centered on the currently selected incident and its affected-radius layer.' : simulation.enabled && selectedIncident ? 'Selected incident location is unavailable.' : selectedIncident ? 'Enable Simulation Mode to display the selected incident on the map.' : selectedConfiguredZoneGeometry?.geometry ? 'The selected configured zone is highlighted and fitted in view. Selection does not activate an alert.' : selectedConfiguredZone ? 'Selected zone geometry is unavailable.' : 'Select a configured zone or enable simulation and choose an incident to focus the map.'}</p></div><MapPin className="h-5 w-5 text-cyan-200" /></div>
            <div className="h-[390px] overflow-hidden rounded-2xl"><MapView key={adminMapKey} zones={zones} simulatedLocation={activeMapIncident ? null : simulationLocation} simulatedCitizens={simulation.enabled ? (demoRecipientPreview?.citizens || simulatedCitizenLocations) : []} incidentLocation={activeMapIncident ? { lat: activeMapIncident.latitude, lng: activeMapIncident.longitude, title: activeMapIncident.title, location: `${activeMapIncident.location_name}, ${activeMapIncident.district} · Approximate incident location`, date: formatIncidentDate(activeMapIncident.date), risk: activeMapIncident.demo_risk, status: 'Active simulation' } : null} incidentRadiusMeters={activeMapIncident?.affected_radius_meters || 0} recipientLocations={recipientPreview?.recipients || []} selectedZone={selectedConfiguredZoneGeometry} selectedZoneRisk={affectedRisk} selectedZoneDuration={affectedDuration} risk={activeMapIncident?.demo_risk || (simulation.enabled ? simulation.effective_risk : (data.events[0]?.final_risk || 'SAFE'))} simulation={simulation.enabled} landslideRecords={data.landslides} /></div>
          </div>
          <div className="rounded-3xl border border-white/8 bg-[#0c1724] p-5">
            <h2 className="font-semibold">Risk overview</h2><p className="mt-1 text-xs text-slate-400">Counts are derived from persisted location events.</p>
            <div className="mt-5 space-y-3">{RISK_ORDER.map((risk) => <div key={risk} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.03] px-3 py-3"><RiskPill value={risk} /><span className="text-xl font-bold">{data.stats?.risk_summary?.[risk] ?? 0}</span></div>)}</div>
            <div className="mt-5 border-t border-white/8 pt-4"><h3 className="text-sm font-semibold">Landslide Inventory</h3><p className="mt-2 text-2xl font-bold text-violet-200">{data.stats?.landslide_inventory?.records ?? 0}</p><p className="mt-1 text-xs text-slate-400">{data.stats?.landslide_inventory?.source || 'Field-validated landslide inventory'} · historical dataset</p><p className="mt-1 text-xs text-slate-500">Year range: {data.stats?.landslide_inventory?.date_range?.from ?? 'unknown'}–{data.stats?.landslide_inventory?.date_range?.to ?? 'unknown'}. Context only; does not trigger alerts.</p></div>
            <div className="mt-5 border-t border-white/8 pt-4"><h3 className="text-sm font-semibold">System status</h3>{Object.entries(data.stats?.system || {}).map(([name, status]) => <div className="mt-3 flex items-center justify-between text-sm" key={name}><span className="capitalize text-slate-400">{name}</span><span className="text-emerald-200">{String(status).replace('-', ' ')}</span></div>)}</div>
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-2">
          <div className="rounded-3xl border border-white/8 bg-[#0c1724] p-5"><h2 className="font-semibold">Recent alerts</h2><p className="mt-1 text-xs text-slate-400">No sensitive message content is shown.</p><div className="mt-4 space-y-3">{data.alerts.length ? data.alerts.map((alert) => <div key={alert.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/8 bg-white/[0.03] p-3"><div><RiskPill value={alert.risk_level} /><p className="mt-2 text-xs text-slate-400">{displayTime(alert.timestamp)}</p></div><span className="text-right text-xs text-slate-300">{alert.status || 'recorded'}</span></div>) : <p className="rounded-xl border border-white/8 p-4 text-sm text-slate-400">No active alerts.</p>}</div></div>
          <div className="rounded-3xl border border-white/8 bg-[#0c1724] p-5"><h2 className="font-semibold">Recent location events</h2><p className="mt-1 text-xs text-slate-400">Latest risk observations recorded by the platform.</p><div className="mt-4 space-y-3">{data.events.length ? data.events.slice(0, 6).map((event) => <div key={event.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/8 bg-white/[0.03] p-3"><div><RiskPill value={event.final_risk} /><p className="mt-2 text-xs text-slate-400">{displayTime(event.timestamp_utc)} · {Number(event.rainfall_mm || 0).toFixed(1)} mm rainfall</p></div><span className="text-right text-xs text-slate-300">{event.geofence_event || event.active_zone_id || 'location update'}</span></div>) : <p className="rounded-xl border border-white/8 p-4 text-sm text-slate-400">No location events have been recorded.</p>}</div></div>
        </section>

        <section className="rounded-3xl border border-white/8 bg-[#0c1724] p-5"><div className="flex items-end justify-between gap-4"><div><h2 className="font-semibold">User monitoring</h2><p className="mt-1 text-xs text-slate-400">Safe identity fields only; data is paginated by the API.</p></div><Link to="/" className="text-sm text-cyan-200 hover:text-cyan-100">Citizen view</Link></div><div className="mt-4 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b border-white/10 text-slate-400"><tr><th className="px-3 py-3">User ID</th><th className="px-3 py-3">Phone</th><th className="px-3 py-3">Role</th><th className="px-3 py-3">Last updated</th><th className="px-3 py-3">Status</th></tr></thead><tbody>{data.users.map((user) => <tr key={user.user_id} className="border-b border-white/5"><td className="px-3 py-3 font-mono text-xs">{user.user_id}</td><td className="px-3 py-3">{user.phone_masked}</td><td className="px-3 py-3">{user.role}</td><td className="px-3 py-3 text-slate-400">{displayTime(user.last_updated)}</td><td className="px-3 py-3 text-slate-300">{user.status}</td></tr>)}{!loading && !data.users.length ? <tr><td colSpan="5" className="px-3 py-6 text-center text-slate-400">No users available.</td></tr> : null}</tbody></table></div></section>
      </div>
    </main>
  )
}
