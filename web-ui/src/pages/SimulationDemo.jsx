import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { apiFetch } from '../auth/authClient'
import MapView from '../shared/MapView'
import '../styles/simulation-demo.css'
import { buildSimulationScenario, SIMULATION_LOCATIONS } from '../services/localSimulation'
import { scenarioKey, toggleRecipient, toggleDemoAdmin, exportSelections, activeAdminActor, simulationExcelFilename } from '../services/simulationRecipients'
import { SIMULATION_MESSAGE_LANGUAGE_ENABLED } from '../data/simulationMessageTranslations'
import { buildSimulationMessage, estimateSmsSegments } from '../services/simulationMessage'

const LOCATIONS = SIMULATION_LOCATIONS
const EMPTY = []
const card = 'simulation-panel'
const button = 'simulation-button'
function detail(error) {
  try { return JSON.parse(error.message).detail || error.message } catch { return error.message }
}

export default function SimulationDemo() {
  const { token, profile } = useAuth()
  const [params, setParams] = useSearchParams()
  const location = LOCATIONS.includes(params.get('location')) ? params.get('location') : 'Madikeri'
  const risk = params.get('risk') === 'CRITICAL' ? 'CRITICAL' : 'HIGH'
  const [reset, setReset] = useState(false)
  const [editing, setEditing] = useState(false)
  const [routeReady, setRouteReady] = useState(true)
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [workbook, setWorkbook] = useState(null)
  const pendingReview = useLocation().state?.recipientReview
  const [drafts, setDrafts] = useState(() => pendingReview?.scenario ? {
    [scenarioKey(pendingReview.scenario.location, pendingReview.scenario.risk)]: pendingReview,
  } : {})
  const [scenario, setScenario] = useState(null)
  const [loading, setLoading] = useState(false)
  const key = scenarioKey(location, risk)
  const message = drafts[key]?.message ?? ''
  const messageLanguage = drafts[key]?.messageLanguage || 'en'
  const messageSegments = estimateSmsSegments(message)
  const selectedIds = drafts[key]?.selected || EMPTY
  const selectedAdmins = drafts[key]?.demoAdmins || EMPTY
  const selections = exportSelections(drafts)
  const selectionKey = JSON.stringify({ location, risk, selections })
  const revision = useRef(0)
  const demo = useMemo(() => buildSimulationScenario(location, risk), [location, risk, refresh])
  const current = !reset && scenario?.location === location && scenario?.risk === risk
  const people = current ? scenario.people : EMPTY
  const inside = people.filter(person => person.inside)
  const eligible = inside.filter(person => person.recipientEligible)
  const outside = people.filter(person => !person.inside)
  const demoAdminRecipients = current ? scenario.demoAdminRecipients || EMPTY : EMPTY
  const canDownload = current && !busy && !loading && workbook?.selectionKey === selectionKey
  useEffect(() => { setWorkbook(null) }, [selectionKey, token])
  useEffect(() => {
    revision.current++
    let active = true
    setScenario(null); setWorkbook(null); setError(''); setNotice(''); setEditing(false); setRouteReady(true)
    if (reset) { setLoading(false); return }
    setLoading(true)
    Promise.allSettled([
      apiFetch(`/admin/simulation/visual/recipients?location=${encodeURIComponent(location)}&risk=${risk}`, {}, token),
      apiFetch('/admin/simulation/visual/demo-admin-recipients', {}, token),
    ]).then(([registered, admins]) => {
        if (!active) return
        if (registered.status === 'rejected') throw registered.reason
        const result = { ...registered.value,
          demoAdminRecipients: admins.status === 'fulfilled' ? admins.value.recipients : [],
          demoAdminError: admins.status === 'rejected' ? detail(admins.reason) : '',
        }
        setScenario(result)
        setDrafts(previous => {
          const old = previous[key]
          const sameScenario = old?.scenario.revision === result.revision
          const selected = sameScenario ? old.selected : []
          const nextLanguage = old?.messageLanguage || 'en'
          const nextMessage = sameScenario ? old.message : nextLanguage === 'en' ? result.message : buildSimulationMessage(result.location, result.risk, nextLanguage)
          const demoAdmins = (old?.demoAdmins || []).filter(id => result.demoAdminRecipients.some(admin => admin.recipientId === id && admin.selectable))
          return { ...previous, [key]: { ...old, scenario: result, selected, demoAdmins, message: nextMessage, messageLanguage: nextLanguage, messageEdited: sameScenario ? old.messageEdited : false } }
        })
      })
      .catch(err => { if (active) setError(detail(err)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false; revision.current++ }
  }, [key, refresh, reset, token])

  function select(nextLocation, nextRisk) {
    revision.current++; setNotice(''); setReset(false)
    setParams({ location: nextLocation, risk: nextRisk })
  }
  function changeMessageLanguage(nextLanguage) {
    if (drafts[key]?.messageEdited && !window.confirm('Replace your edited message?')) return
    setDrafts(previous => ({ ...previous, [key]: { ...previous[key], messageLanguage: nextLanguage, message: buildSimulationMessage(location, risk, nextLanguage), messageEdited: false } }))
    setNotice('')
  }
  async function generateExcel() {
    if (!selections.length) { setError('Select at least one recipient to generate the Excel.'); return }
    if (!current || busy || selections.some(item => !item.message.trim())) return
    const generation = revision.current
    setBusy(true); setWorkbook(null); setError(''); setNotice('')
    try {
      const blob = await apiFetch('/admin/simulation/visual/registered-excel', { method: 'POST', body: JSON.stringify({ scenarios: selections }) }, token, 'blob')
      if (generation !== revision.current) return
      setWorkbook({ blob, filename: simulationExcelFilename(selections), selectionKey })
      setNotice(`Excel generated successfully for ${selections.length} location/risk selections. Only explicitly selected recipients are included. Select Download Excel to save the workbook, then upload manually to httpSMS; no SMS was sent.`)
    } catch (err) { if (generation === revision.current) setError(detail(err)) }
    finally { setBusy(false) }
  }
  function download() {
    if (!canDownload) return
    let url
    let link
    setError('')
    try {
      url = URL.createObjectURL(workbook.blob)
      link = document.createElement('a')
      link.href = url
      link.download = workbook.filename
      document.body.appendChild(link); link.click(); link.remove()
      setNotice('Excel downloaded successfully.')
    } catch { setNotice(''); setError('Unable to download the generated Excel. Please try again.') }
    finally {
      link?.remove()
      if (url) setTimeout(() => URL.revokeObjectURL(url), 1000)
    }
  }
  return <main className="simulation-shell"><div className="simulation-container">
    <header className="simulation-header">
      <div className="simulation-brand"><Link to="/admin" className="simulation-back">← Back to Admin</Link><p>LAND<span>sense</span></p><h1>Emergency Simulation</h1></div>
      <div className="simulation-warning"><strong>SIMULATION MODE</strong><span>DEMONSTRATION ONLY</span></div>
      <div className="simulation-identity"><span>Administrator</span><strong>{profile?.name || profile?.phone_number_masked || 'Admin'}</strong></div>
    </header>
    <p className="simulation-intro">Demonstrates how LandSense responds when users are detected inside a landslide danger zone.</p>
    <div className="simulation-workspace">
      <section className={card} aria-label="Simulation control">
        <h2>Simulation Controls</h2>
        <label className="mt-4 block text-sm">Location<select disabled={busy || loading} value={reset ? "" : location} onChange={e => select(e.target.value, risk)} className="simulation-input">{reset ? <option value="">Select location</option> : null}{LOCATIONS.map(name => <option key={name}>{name}</option>)}</select></label>
        <label className="mt-4 block text-sm">Risk Level<select disabled={busy || loading} value={reset ? "" : risk} onChange={e => select(location, e.target.value)} className="simulation-input">{reset ? <option value="">Select risk</option> : null}<option>HIGH</option><option>CRITICAL</option></select></label>
        <dl className="simulation-stats">{[['Affected users', inside.length], ['Excluded users', outside.length], ['Safe route', current && routeReady ? 'Available' : 'Pending'], ['Eligible Users', eligible.length], ['Selected Recipients', selectedIds.length]].map(([label, value]) => <div key={label} className="flex justify-between gap-2"><dt>{label}</dt><dd className="font-bold">{value}</dd></div>)}</dl>
        {current && routeReady ? <p className="mb-4 text-xs simulation-secondary">Safe destination: {demo.route.safe_zone.name}<br />Distance: {demo.route.route.distance_meters} m · Estimated evacuation: {demo.route.route.estimated_minutes} min<br /><span className="simulation-secondary">Simulation estimate · assembly point {demo.route.route.boundary_distance_meters} m beyond boundary</span></p> : null}
        <div className="flex flex-col gap-3">
          <button className={button} disabled={busy} onClick={() => { setReset(false); setRefresh(value => value + 1) }}>Recalculate Danger Zone</button>
          <button className={button} disabled={!current || busy} onClick={() => { setRouteReady(true); setNotice('Route calculated by LandSense — deterministic demonstration path. It exits the danger zone once and continues to the simulated safe area.') }}>Calculate Safe Route</button>
          <button className={`${button} simulation-button-primary`} disabled={!current || !selections.length || !message.trim() || busy || loading} onClick={generateExcel}>{busy ? 'Generating…' : 'Generate httpSMS Excel'}</button>
          <button className={button} disabled={!canDownload} onClick={download}>↓ Download Excel</button>
          {!selections.length ? <p className="text-xs simulation-secondary">Select at least one recipient to generate the Excel.</p> : null}
          <button className={button} disabled={busy} onClick={() => { setWorkbook(null); setRouteReady(false); setReset(true); setDrafts({}); setScenario(null); setParams({}); setError(''); setEditing(false); setNotice('Simulation reset. Select Recalculate Danger Zone to restart.'); revision.current++ }}>Reset Simulation</button>
        </div>
        {current && scenario.adminActor?.status !== 'available' ? <p role="status" className="mt-3 simulation-secondary">{scenario.adminActor?.message || 'Admin simulation actor unavailable.'}</p> : null}
        <p className="mt-3 text-xs simulation-actor-note">ADMIN SIMULATION ACTOR: visualization only, not real GPS or an SMS recipient. Your saved location remains unchanged. The existing demonstration route retains its original start point.</p>
        <p className="mt-4 text-xs simulation-secondary">Eligibility uses registered users and their saved locations. Select recipients explicitly; no user records are changed.</p>
      </section>
      <section className={card} aria-label="Simulation map">
        <div className="simulation-map-heading"><h2>Simulation Map</h2><span className="simulation-risk">{location} · {risk} RISK</span></div>
        <p className="mt-1 text-sm simulation-secondary">Danger zone → Safe evacuation path → Safe area</p>
        <div className="simulation-map-frame">
          {current ? <MapView key={`${location}:${risk}:${refresh}`} zones={EMPTY} syntheticZone={demo.dangerZone} simulationRoute={routeReady ? demo.route : null} simulationSafeZone={demo.safeZone} showSimulationLayers={true} affectedUserLocations={people} adminSimulationActor={activeAdminActor(scenario, location, risk, current)} risk={risk} /> : <MapView key="simulation-inactive" zones={EMPTY} />}
        </div>
        {reset ? <p role="status" className="mt-3">Simulation reset. Actor and simulation overlays removed. Recalculate Danger Zone to restart.</p> : null}
        <div className="simulation-map-key"><span className="simulation-danger">● Red: DANGER ZONE</span><span className="simulation-secondary">● Cyan outline: INSIDE / ELIGIBLE</span><span className="simulation-secondary">● Gray: OUTSIDE / EXCLUDED</span><span className="simulation-safe">● Green: SAFE AREA / ROUTE</span></div>
        <p className="mt-3 text-xs simulation-secondary">Route calculated by LandSense. Affected-user center → mapped road exit → nearest valid local assembly candidate. Corridors follow cached roads © <a href="https://www.openstreetmap.org/copyright" className="underline">OpenStreetMap contributors</a>; all segments after the exit remain outside the danger polygon. Assembly sites, distance and walking time are simulation estimates, not verified emergency navigation.</p>
      </section>
    </div>
    {loading ? <p role="status" className="mt-4">Loading registered user eligibility...</p> : null}
    {selections.length ? <section className={`${card} mt-5`} aria-label="Selected location recipients"><h2 className="font-bold">Selected locations</h2>{selections.map(item => <p key={scenarioKey(item.location, item.risk)}>{item.location} &middot; {item.risk}: {item.recipient_ids.length} registered users &middot; {item.demo_admin_recipient_ids?.length || 0} Demo Admin recipients</p>)}</section> : null}
    {error ? <p role="alert" className="simulation-feedback simulation-feedback-error">{error}</p> : null}
    {notice ? <p role="status" className="simulation-feedback simulation-feedback-success">{notice}</p> : null}
    {current ? <>
      <section className={`${card} mt-5`} aria-label="Geofencing analysis"><h2 className="font-semibold">GEOFENCING ANALYSIS</h2>
        <div className="simulation-analysis">{[['Location', location], ['Risk', risk], ['Located Users', people.length], ['Users inside danger zone', inside.length], ['Users outside danger zone', outside.length], ['Eligible Users', eligible.length], ['Selected Recipients', selectedIds.length], ['SMS excluded', outside.length]].map(([label, value]) => <div className="simulation-analysis-item" key={label}><p className="text-xs simulation-secondary">{label}</p><p className="mt-1 font-bold">{value}</p></div>)}</div>
        <p className="mt-3 text-sm simulation-secondary">✓ Eligibility is calculated from registered users' saved locations. Only users physically inside the affected zone are eligible for the emergency message. Only explicitly selected eligible users are exported.</p>
      </section>
      <section className={`${card} mt-5`} aria-label="SMS recipient verification"><h2 className="font-semibold">SMS RECIPIENTS</h2><p className="mt-3 text-sm">✓ {inside.length} users inside danger zone · ✓ {eligible.length} eligible users &middot; {selectedIds.length} selected recipients · ✓ {outside.length} users excluded because they are outside the zone</p>
        <p className="mt-3 text-sm">Eligible Users: {eligible.length} &middot; Selected Recipients: {selectedIds.length}</p><button type="button" className={button} disabled={busy || loading} onClick={() => setDrafts(previous => ({ ...previous, [key]: { ...previous[key], selected: [] } }))}>Clear Selection for This Location</button>
        <div className="simulation-table-scroll"><table className="simulation-table"><thead className="simulation-secondary"><tr>{['Select', 'Registered User', 'Phone', 'Location Status', 'Eligibility'].map(label => <th key={label} className="p-3">{label}</th>)}</tr></thead><tbody>{people.map(person => <tr key={person.displayId} className="simulation-recipient-row"><td className="p-3"><input aria-label={`Select ${person.displayId}`} type="checkbox" disabled={!person.recipientEligible || busy || loading} checked={selectedIds.includes(person.displayId)} onChange={event => setDrafts(previous => ({ ...previous, [key]: { ...previous[key], selected: toggleRecipient(previous[key].selected, person.displayId, event.target.checked, people) } }))} /></td><td className="p-3">{person.displayId}</td><td className="p-3 font-mono">{person.phone}</td><td className="p-3"><span className={`simulation-badge ${person.inside ? 'simulation-badge-danger' : ''}`}>{person.inside ? 'INSIDE DANGER ZONE' : 'OUTSIDE DANGER ZONE'}</span></td><td className="p-3"><span className={`simulation-badge ${person.recipientEligible ? 'simulation-badge-eligible' : ''}`}>{person.recipientEligible ? 'ELIGIBLE' : 'EXCLUDED'}</span></td></tr>)}</tbody></table></div>
      </section>
      <section className={`${card} mt-5`} aria-label="Demo Admin recipients">
        <h2>DEMO ADMIN RECIPIENTS</h2>
        <p className="mt-2 text-sm simulation-secondary">Select Admin accounts to receive this simulation demonstration message.</p>
        <p className="mt-1 text-xs simulation-secondary">Other Admin accounts can be selected regardless of location. No accounts are automatically selected. Excel download only; upload manually to httpSMS.</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button type="button" className={button} disabled={busy || loading || !demoAdminRecipients.some(admin => admin.selectable)} onClick={() => setDrafts(previous => ({ ...previous, [key]: { ...previous[key], demoAdmins: demoAdminRecipients.filter(admin => admin.selectable).map(admin => admin.recipientId) } }))}>Select All</button>
          <button type="button" className={button} disabled={busy || loading || !selectedAdmins.length} onClick={() => setDrafts(previous => ({ ...previous, [key]: { ...previous[key], demoAdmins: [] } }))}>Clear Selection</button>
          <p className="text-sm">Selected Admin Recipients: <strong>{selectedAdmins.length}</strong></p>
        </div>
        {scenario.demoAdminError ? <p role="alert" className="simulation-feedback simulation-feedback-error">{scenario.demoAdminError}</p> : null}
        {!scenario.demoAdminError && !demoAdminRecipients.length ? <p className="mt-3 text-sm simulation-secondary">No other Admin accounts are available.</p> : null}
        <div className="simulation-demo-admin-list">{demoAdminRecipients.map(admin => <label key={admin.recipientId} className="simulation-demo-admin-row">
          <input type="checkbox" aria-label={`Select Demo Admin ${admin.name}`} disabled={busy || loading || !admin.selectable} checked={selectedAdmins.includes(admin.recipientId)} onChange={event => setDrafts(previous => ({ ...previous, [key]: { ...previous[key], demoAdmins: toggleDemoAdmin(previous[key].demoAdmins || [], admin.recipientId, event.target.checked, demoAdminRecipients) } }))} />
          <span><strong>{admin.name}</strong><span className="block text-xs simulation-secondary">{admin.phone}{!admin.selectable ? ' · Valid registered phone required' : ''}</span></span>
          <span className="simulation-badge">ADMIN</span>
        </label>)}</div>
      </section>
      <section className={`${card} mt-5`} aria-label="Emergency message preview"><h2 className="font-semibold">SIMULATION MESSAGE</h2><p className="mt-2 text-sm">Location: {location} · Risk: {risk} · Selected Recipients: {selectedIds.length} registered users · {selectedAdmins.length} Demo Admins</p>
        {SIMULATION_MESSAGE_LANGUAGE_ENABLED ? <label className="mt-4 block text-sm">Message language<select className="simulation-input" value={messageLanguage} onChange={event => changeMessageLanguage(event.target.value)}><option value="en">English</option><option value="kn">ಕನ್ನಡ (Kannada)</option><option value="both">English + Kannada</option></select></label> : null}
        <label htmlFor="simulation-message" className="mt-4 block text-sm">Message</label><textarea id="simulation-message" lang={messageLanguage === 'en' ? 'en' : 'kn'} readOnly={!editing || busy} value={message} maxLength={1000} rows={5} onChange={e => { setDrafts(previous => ({ ...previous, [key]: { ...previous[key], message: e.target.value, messageEdited: true } })); setNotice('') }} className="simulation-input simulation-message" />
        <p className="mt-2 text-xs simulation-secondary">This message is used only in the generated simulation httpSMS Excel.</p>
        <p className="mt-1 text-xs simulation-secondary">{message.length}/1000 characters{SIMULATION_MESSAGE_LANGUAGE_ENABLED ? ` · ${messageSegments.segments} SMS segment${messageSegments.segments === 1 ? '' : 's'} (${messageSegments.encoding}; ${messageSegments.singleSegmentLimit} single / ${messageSegments.splitSegmentLimit} split)` : ''}. Exports always carry a SIMULATION ONLY prefix.</p>
        {SIMULATION_MESSAGE_LANGUAGE_ENABLED && messageSegments.segments > 1 ? <p role="status" className="mt-1 text-xs simulation-feedback-error">This message uses {messageSegments.segments} SMS segments.</p> : null}
        <div className="mt-4 flex flex-wrap gap-3"><button className={button} disabled={busy} onClick={() => setEditing(value => !value)}>{editing ? 'Finish Editing' : 'Edit Message'}</button><button className={button} disabled={busy || loading || !selections.length || !message.trim()} onClick={generateExcel}>{busy ? 'Generating…' : 'Generate Excel'}</button><button className={`${button} border-[#176B52] text-[#176B52]`} disabled={!canDownload} onClick={download}>↓ Download Excel</button></div>
        <p className="mt-4 text-xs simulation-secondary">Excel columns: FromPhoneNumber · ToPhoneNumber · Content · SendTime(optional). Sender uses HTTPSMS_FROM_NUMBER; send time stays blank. No SMS is automatically sent.</p>
      </section>
      <section className={`${card} mt-5`} aria-label="Simulation timeline"><h2 className="font-semibold">SIMULATION TIMELINE</h2><p className="mt-2 text-xs simulation-secondary">Admin selects {location} → selects {risk} → LandSense identifies the zone, checks users, filters recipients, calculates the route and generates Excel.</p><ol className="simulation-timeline">{['DANGER DETECTED', 'GEOFENCE CREATED', 'USERS LOCATED', 'AFFECTED USERS IDENTIFIED', 'SAFE ROUTE CALCULATED', 'EMERGENCY MESSAGE GENERATED', 'SMS EXCEL READY'].map((label, index) => <li key={label} className="simulation-timeline-event"><p className="font-semibold simulation-secondary">{String(index + 1).padStart(2, '0')}</p><p className="mt-2 text-xs font-bold">{label}</p><p className="mt-2 text-xs simulation-secondary">{index === 6 ? canDownload ? 'Complete' : 'Awaiting generation' : index === 4 && !routeReady ? 'Pending' : 'Complete'}</p></li>)}</ol></section>
    </> : null}
  </div></main>
}
