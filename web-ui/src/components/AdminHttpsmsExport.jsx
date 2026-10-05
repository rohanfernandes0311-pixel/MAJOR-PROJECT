import { useEffect, useState } from 'react'
import { apiFetch } from '../auth/authClient'

function errorText(error) {
  try { return JSON.parse(error.message).detail || error.message } catch { return error.message || 'Unable to prepare httpSMS export.' }
}

export default function AdminHttpsmsExport({ zoneId, simulationEnabled, token, selectedRecipientIds = null, demo = null }) {
  const [localSelection, setLocalSelection] = useState([])
  useEffect(() => { setLocalSelection([]) }, [zoneId, simulationEnabled, demo?.scenarioRevision])
  const recipientIds = selectedRecipientIds ?? localSelection
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const selection = recipientIds.join(',')
  const requestKey = JSON.stringify([zoneId, simulationEnabled, selection, demo?.scenarioRevision, demo?.message])
  const [previewKey, setPreviewKey] = useState('')
  const demoBody = { scenario_revision: demo?.scenarioRevision, message: demo?.message, recipient_ids: recipientIds }
  useEffect(() => {
    let current = true
    setPreview(null)
    setError('')
    if (!zoneId || !simulationEnabled) return
    setLoading(true)
    const selectionQuery = `?recipient_ids=${encodeURIComponent(recipientIds.join(','))}`
    const path = demo ? '/admin/simulation/demo/httpsms-preview' : `/admin/affected-zones/${encodeURIComponent(zoneId)}/httpsms-preview${selectionQuery}`
    apiFetch(path, demo ? { method: 'POST', body: JSON.stringify(demoBody) } : {}, token)
      .then((result) => { if (current) { setPreview(result); setPreviewKey(requestKey) } })
      .catch((err) => { if (current) setError(errorText(err)) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [requestKey, token, refresh])

  async function download() {
    if (!selected || !preview?.download_enabled || downloading) return
    setDownloading(true)
    setError('')
    try {
      const selectionQuery = `&recipient_ids=${encodeURIComponent(recipientIds.join(','))}`
      const path = demo ? '/admin/simulation/demo/httpsms-excel' : `/admin/affected-zones/${encodeURIComponent(zoneId)}/httpsms-excel?revision=${encodeURIComponent(preview.revision)}${selectionQuery}`
      const blob = await apiFetch(path, demo ? { method: 'POST', body: JSON.stringify({ ...demoBody, revision: preview.revision }) } : {}, token, 'blob')
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = preview.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) { setError(errorText(err)) }
    finally { setDownloading(false) }
  }

  const selected = simulationEnabled && preview?.zone_id === zoneId && previewKey === requestKey
  return <section className="mt-4 rounded-xl border border-cyan-300/25 bg-cyan-400/5 p-4" aria-label="httpSMS Excel export">
    <h3 className="font-bold">httpSMS Excel Export</h3>
    <p className="mt-1 text-xs text-slate-300">Select a configured HIGH / CRITICAL zone in Simulation Mode. Download the recipient file, then manually upload it to httpSMS for Android phone/SIM delivery.</p>
    {!simulationEnabled ? <p className="mt-2 text-amber-200">Enable Simulation Mode to prepare an export.</p> : !zoneId ? <p className="mt-2">Select a danger zone.</p> : null}
    {loading && simulationEnabled && zoneId ? <p role="status">Calculating affected users...</p> : null}
    {selected ? <div className="mt-3 text-sm">
      <p>Simulation: {preview.risk_level} — {preview.location}</p>
      <p>Eligible Users: {preview.eligible_count}</p><p>Selected Recipients: {preview.selected_count}</p>
      {selectedRecipientIds === null ? <div className="mt-3 space-y-2">{preview.recipients.map(person => <label key={person.display_id} className="flex gap-2">
        <input type="checkbox" disabled={!person.sms_eligible || downloading} checked={localSelection.includes(person.display_id)} onChange={event => setLocalSelection(ids => event.target.checked ? [...new Set([...ids, person.display_id])] : ids.filter(id => id !== person.display_id))} />
        <span>{person.display_id} — {person.phone_masked}{!person.sms_eligible ? ' (unavailable)' : ''}</span>
      </label>)}</div> : null}
      <p>Duplicate numbers excluded: {preview.duplicate_count}</p>
      {preview.invalid_recipients.length ? <p className="text-amber-200">Invalid numbers excluded: {preview.invalid_recipients.join(', ')}</p> : null}
      <p className="mt-2 text-slate-300">{preview.message}</p>
      {preview.error ? <p role="alert" className="mt-2 text-amber-200">{preview.error}</p> : null}
    </div> : null}
    {error ? <p role="alert" className="mt-2 text-rose-200">{error}</p> : null}
    <div className="mt-3 flex gap-3">
      <button type="button" onClick={download} disabled={!selected || loading || downloading || !preview?.download_enabled} className="rounded-lg bg-cyan-300 px-4 py-2 font-bold text-slate-950 disabled:opacity-50">{downloading ? 'Preparing Excel...' : 'Download httpSMS Excel'}</button>
      <button type="button" onClick={() => setRefresh((value) => value + 1)} disabled={!simulationEnabled || !zoneId || loading || downloading} className="rounded-lg border border-white/20 px-3 py-2 disabled:opacity-50">Refresh recipients</button>
    </div>
  </section>
}
