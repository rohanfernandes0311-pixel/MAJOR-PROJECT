import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../auth/authClient'

const LOCATIONS = ['Madikeri', 'Virajpet', 'Chittalli', 'Perumbadi', 'Makutta']
const RISKS = ['HIGH', 'CRITICAL']

// Local demo controls deliberately do not update Admin's live simulation state.
export default function AdminKodaguSimulation({ token }) {
  const [location, setLocation] = useState('Madikeri')
  const [risk, setRisk] = useState('HIGH')
  const [scenario, setScenario] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedRecipientIds, setSelectedRecipientIds] = useState([])
  const path = `/admin/simulation/demo?location=${encodeURIComponent(location)}&risk=${risk}`
  async function create() {
    setBusy(true); setError(''); setPreview(false); setNotice(''); setScenario(null)
    try {
      const result = await apiFetch(`/admin/simulation/visual/recipients?location=${encodeURIComponent(location)}&risk=${risk}`, {}, token)
      setScenario(result)
      setSelectedRecipientIds([])
    } catch (err) {
      try { setError(JSON.parse(err.message).detail || err.message) } catch { setError(err.message) }
    } finally { setBusy(false) }
  }
  function change(nextLocation, nextRisk) {
    setLocation(nextLocation); setRisk(nextRisk); setScenario(null); setPreview(false); setNotice(''); setError(''); setSelectedRecipientIds([])
  }
  return <section className="rounded-3xl border border-amber-300/35 bg-[#111526] p-5 text-slate-100" aria-labelledby="kodagu-simulation-heading">
    <div className="flex flex-wrap items-start justify-between gap-3"><div>
      <p className="text-xs font-black tracking-[0.18em] text-amber-200">KODAGU EMERGENCY SIMULATION</p>
      <h2 id="kodagu-simulation-heading" className="mt-1 text-xl font-black">SIMULATION MODE — DEMONSTRATION ONLY</h2>
      <p className="mt-1 text-sm text-amber-100">Simulation only. Eligibility uses saved registered-user locations; no production alerts are sent.</p>
    </div><span className="rounded-full bg-blue-500/20 px-3 py-1 text-xs font-black text-blue-200">Status: SIMULATION ONLY</span></div>
    <Link to={path} aria-disabled={!location || !risk} onClick={event => { if (!location || !risk) event.preventDefault() }} state={{ recipientReview: scenario ? { scenario, selected: selectedRecipientIds, message: scenario.message } : null }} className="mt-4 inline-block rounded-xl border border-cyan-300/40 px-4 py-2 font-bold text-cyan-100">Open Simulation Demonstration</Link>
    <div className="mt-5 grid gap-4 md:grid-cols-[1fr_1fr_auto]">
      <label className="text-sm">Location<select value={location} disabled={busy} onChange={e => change(e.target.value, risk)} className="mt-1 block w-full rounded-xl border border-white/15 bg-[#091521] px-3 py-2"><option value="">Select location</option>{LOCATIONS.map(name => <option key={name}>{name}</option>)}</select></label>
      <fieldset><legend className="text-sm">Simulation Risk Level</legend><div className="mt-1 flex gap-2">{RISKS.map(level => <button key={level} type="button" disabled={busy} onClick={() => change(location, level)} className={`rounded-xl border px-4 py-2 text-sm font-black ${risk === level ? 'border-rose-300 bg-rose-500/25 text-rose-100' : 'border-white/15'}`}>{level}</button>)}</div></fieldset>
      <div className="flex items-end"><button type="button" onClick={create} disabled={busy || !location || !risk} className="rounded-xl bg-amber-300 px-4 py-2 font-black text-slate-950 disabled:opacity-50">{busy ? 'Creating…' : 'Create Synthetic Zone'}</button></div>
    </div>
    {scenario ? <div className="mt-5 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm">
      <b>{scenario.location} · {scenario.risk} SIMULATION</b>
      <p className="mt-2">Generated synthetic zone for simulation. Registered users: {scenario.people.filter(p => p.inside).length} inside and {scenario.people.filter(p => !p.inside).length} outside. Safe evacuation route available on the demonstration page.</p>
      <details className="mt-4"><summary className="cursor-pointer font-bold">Affected Users — simulated only</summary>
        <div className="mt-3 flex gap-2"><button type="button" onClick={() => setSelectedRecipientIds(scenario.people.filter(p => p.recipientEligible).map(p => p.displayId))} className="rounded-lg border border-cyan-300/30 px-3 py-1.5">Select All Eligible</button><button type="button" onClick={() => setSelectedRecipientIds([])} className="rounded-lg border border-white/20 px-3 py-1.5">Clear Selection</button></div>
        {scenario.people.map(person => <label key={person.displayId} className="mt-2 flex gap-2 rounded-lg bg-white/5 p-2"><input type="checkbox" disabled={!person.recipientEligible} checked={selectedRecipientIds.includes(person.displayId)} onChange={e => setSelectedRecipientIds(values => e.target.checked ? [...new Set([...values, person.displayId])] : values.filter(id => id !== person.displayId))} /><span>{person.displayId} · {person.inside ? 'Inside / eligible' : 'Outside / excluded'}</span></label>)}
      </details>
      <div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={() => setPreview(true)} className="rounded-xl bg-rose-500 px-4 py-2 font-bold">Trigger Alert Preview</button><button type="button" onClick={() => { setScenario(null); setSelectedRecipientIds([]); setLocation(''); setRisk(''); setPreview(false); setNotice('Simulation reset.'); setError('') }} className="rounded-xl border border-white/20 px-4 py-2">Reset Simulation</button></div>
    </div> : null}
    {preview && scenario ? <div className="mt-4 rounded-2xl border border-rose-300/30 p-4" role="dialog" aria-label="Alert preview"><h3 className="font-black">ALERT PREVIEW</h3><p className="mt-2">{scenario.message}</p><p className="mt-2">Selected recipients: {selectedRecipientIds.length}</p><p className="mt-2 text-xs text-amber-200">It does not send SMS. Your explicit selection is carried to the demonstration page for review and Excel export.</p><div className="mt-3 flex gap-3"><button onClick={() => { setPreview(false); setNotice('Recipient selection confirmed locally. Open Simulation Demonstration to review and export. No SMS was sent.') }} className="rounded-xl bg-rose-500 px-4 py-2">Confirm Demo Alert</button><button onClick={() => setPreview(false)} className="rounded-xl border border-white/20 px-4 py-2">Cancel</button></div></div> : null}
    <p className="mt-4 text-sm text-slate-300">Preview/edit the message, verify recipients and download httpSMS Excel on the dedicated demonstration page. No SMS is sent automatically.</p>
    {error ? <p role="alert" className="mt-4 text-rose-200">{error}</p> : null}{notice ? <p role="status" className="mt-4 text-emerald-200">{notice}</p> : null}
    <p className="mt-5 text-xs text-slate-400">HIGH and CRITICAL are LandSense demonstration states. Synthetic boundaries, routes and shelters are illustrative and are not official hazard classifications.</p>
  </section>
}
