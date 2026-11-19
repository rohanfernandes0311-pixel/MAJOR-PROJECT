import { useCallback, useEffect, useRef, useState } from 'react'
import MapView from '../shared/MapView'
import { apiFetch, getStoredAuth } from '../auth/authClient'
import CommunityReportLocationMap from './CommunityReportLocationMap'
import {
  COMMUNITY_REPORTS_ENHANCED,
  citizenReportStatusLabel,
  isWithinKarnatakaBounds,
  reverseKarnatakaPlace,
  searchKarnatakaPlaces,
} from '../services/communityReportsFeature'

const CATEGORIES = [
  ['landslide', 'Landslide'], ['road_blockage', 'Road blockage due to landslide'],
  ['rockfall', 'Rockfall'], ['soil_erosion', 'Soil erosion'],
  ['ground_cracks', 'Cracks or ground movement'], ['other', 'Other hazard'],
]
const STATUS_LABELS = {
  pending: 'Pending', under_review: 'Under Review',
  verified: COMMUNITY_REPORTS_ENHANCED ? 'Approved' : 'Verified', rejected: 'Rejected',
}
const EMPTY = []

function submissionErrorMessage(error) {
  if (error?.status === 409) return 'A similar report was just submitted from this location.'
  if (error?.status === 429) return 'You have reached the recent report limit. Please try again later.'
  if (error?.status === 401 || error?.status === 403) return 'Your session cannot submit this report. Please sign in again.'
  if (error?.status === 422) {
    try {
      const detail = JSON.parse(error.message)?.detail
      if (typeof detail === 'string' && /description.*blank|required/i.test(detail)) return 'Description is required.'
      if (typeof detail === 'string') return detail
    } catch { /* use the safe validation fallback */ }
    return 'Check the hazard type, description, and location, then try again.'
  }
  if (error?.status >= 500) return 'The server could not save this report right now. Please try again.'
  if (!error?.status) return 'Could not reach the report service. Check your connection and try again.'
  return 'Report submission failed. Please try again.'
}

function reportDate(value) {
  if (!value) return 'Date unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? 'Date unavailable' : date.toLocaleString()
}

export function CitizenCommunityReports({ location, onSubmitted }) {
  const [form, setForm] = useState({ category: 'landslide', description: '', latitude: '', longitude: '' })
  const [selectedLocation, setSelectedLocation] = useState({ valid: false, placeName: '' })
  const [searchQuery, setSearchQuery] = useState('')
  const [suggestions, setSuggestions] = useState(EMPTY)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [reports, setReports] = useState(EMPTY)
  const [reportsLoadStatus, setReportsLoadStatus] = useState('loading')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const locationRequestRef = useRef(0)
  const selectedPlaceLabelRef = useRef('')

  const loadReports = useCallback(async () => {
    setReportsLoadStatus('loading')
    try {
      const response = await apiFetch('/community-reports/mine?limit=20&offset=0', {}, getStoredAuth().token)
      setReports(response.reports || EMPTY)
      setReportsLoadStatus('success')
    } catch {
      setReportsLoadStatus('error')
    }
  }, [])

  useEffect(() => { void loadReports() }, [loadReports])
  useEffect(() => {
    if (COMMUNITY_REPORTS_ENHANCED || !location || form.latitude || form.longitude) return
    setForm((current) => ({ ...current, latitude: String(location.lat), longitude: String(location.lng) }))
  }, [form.latitude, form.longitude, location])

  useEffect(() => {
    if (!COMMUNITY_REPORTS_ENHANCED || searchQuery.trim().length < 3 || searchQuery === selectedPlaceLabelRef.current) {
      setSuggestions(EMPTY)
      setSearchLoading(false)
      setSearchError('')
      return undefined
    }
    const controller = new AbortController()
    let stale = false
    const timer = window.setTimeout(() => {
      setSearchLoading(true)
      setSearchError('')
      searchKarnatakaPlaces(searchQuery, { signal: controller.signal })
        .then((results) => {
          if (stale) return
          setSuggestions(results)
        })
        .catch((err) => {
          if (!stale && err.name !== 'AbortError') setSearchError(err.message || 'Place search is unavailable. Please try again.')
        })
        .finally(() => { if (!stale) setSearchLoading(false) })
    }, 300)
    return () => { stale = true; window.clearTimeout(timer); controller.abort() }
  }, [searchQuery])

  function applyPlace(place) {
    locationRequestRef.current += 1
    selectedPlaceLabelRef.current = place.label
    setSelectedLocation({ ...place, valid: true, checking: false })
    setForm((current) => ({ ...current, latitude: String(place.latitude), longitude: String(place.longitude) }))
    setSearchQuery(place.label)
    setSuggestions(EMPTY)
    setSearchError('')
  }

  async function chooseCoordinates(point) {
    const requestId = ++locationRequestRef.current
    const latitude = Number(point.latitude)
    const longitude = Number(point.longitude)
    setForm((current) => ({ ...current, latitude: '', longitude: '' }))
    if (!isWithinKarnatakaBounds(latitude, longitude)) {
      setSelectedLocation({ valid: false, checking: false, placeName: '' })
      setSearchError('Choose a location within Karnataka, India.')
      return
    }
    setSelectedLocation({ valid: false, checking: true, placeName: '', latitude, longitude })
    setSearchError('Checking that location is within Karnataka...')
    try {
      const place = await reverseKarnatakaPlace(latitude, longitude)
      if (requestId !== locationRequestRef.current) return
      applyPlace(place)
    } catch (err) {
      if (requestId !== locationRequestRef.current) return
      setSelectedLocation({ valid: false, checking: false, placeName: '' })
      setSearchError(err.message || 'Choose a location within Karnataka, India.')
    }
  }

  function useCurrentLocation() {
    setSearchError('Finding your current location...')
    if (!navigator.geolocation) {
      setSearchError('Location is not available in this browser. Search for a place or select it on the map.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => { void chooseCoordinates({ latitude: coords.latitude, longitude: coords.longitude }) },
      () => setSearchError('Could not get your location. Allow location access or search for a place.'),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    )
  }

  async function submit(event) {
    event.preventDefault()
    if (COMMUNITY_REPORTS_ENHANCED && (!selectedLocation.valid || !isWithinKarnatakaBounds(form.latitude, form.longitude))) {
      setError('Choose a valid location in Karnataka before submitting.')
      return
    }
    if (COMMUNITY_REPORTS_ENHANCED && (!form.category || !form.description.trim())) {
      setError('Choose a hazard type and enter a description before submitting.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await apiFetch('/community-reports', {
        method: 'POST',
        body: JSON.stringify({
          category: form.category,
          description: form.description,
          latitude: Number(form.latitude),
          longitude: Number(form.longitude),
          ...(COMMUNITY_REPORTS_ENHANCED ? { place_name: selectedLocation.label } : {}),
        }),
      }, getStoredAuth().token)
      setForm((current) => ({ ...current, description: '' }))
      setMessage('Report submitted. It will appear as unverified until reviewed by an administrator.')
      await loadReports()
      onSubmitted?.()
    } catch (err) {
      console.error('Community report submission failed', err)
      setError(submissionErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const locationIsValid = COMMUNITY_REPORTS_ENHANCED
    ? selectedLocation.valid && isWithinKarnatakaBounds(form.latitude, form.longitude)
    : Boolean(form.latitude && form.longitude)
  const submitDisabled = loading || (COMMUNITY_REPORTS_ENHANCED && (!form.category || !form.description.trim() || !locationIsValid))

  return <section className={`border border-[#dfe5df] bg-white p-4 ${COMMUNITY_REPORTS_ENHANCED ? 'citizen-community-reports col-span-full' : ''}`} aria-labelledby="community-report-title">
    <div className="section-kicker">Community reports</div>
    <h2 id="community-report-title" className="mt-1 text-sm font-semibold text-slate-900">Report a local hazard</h2>
    <p className="mt-1 text-xs text-slate-600">Reports are community observations. They do not change official risk scores or hazard zones.</p>
    <div className={COMMUNITY_REPORTS_ENHANCED ? 'mt-3 grid gap-4 lg:grid-cols-2' : 'mt-3'}>
      <div>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-xs font-semibold text-slate-700">Hazard type
            <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="block text-xs font-semibold text-slate-700">What did you observe?
            <textarea required minLength="1" maxLength="2000" rows="3" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Describe the hazard and when you noticed it." />
          </label>
          {COMMUNITY_REPORTS_ENHANCED ? <>
            <p className="text-[11px] text-slate-500">The report location is selected on the map or by place search; coordinates are saved automatically.</p>
          </> : <>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs font-semibold text-slate-700">Latitude<input required type="number" min="-90" max="90" step="any" value={form.latitude} onChange={(event) => setForm({ ...form, latitude: event.target.value })} className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
              <label className="text-xs font-semibold text-slate-700">Longitude<input required type="number" min="-180" max="180" step="any" value={form.longitude} onChange={(event) => setForm({ ...form, longitude: event.target.value })} className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
            </div>
            <p className="text-[11px] text-slate-500">Location starts at your current GPS fix when available. No photograph is collected.</p>
          </>}
      <button type="submit" disabled={submitDisabled} className="rounded-lg bg-emerald-800 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{loading ? 'Submitting...' : 'Submit report'}</button>
          {message ? <p role="status" className="text-xs text-emerald-800">{message}</p> : null}
          {error ? <p role="alert" className="text-xs text-rose-700">{error}</p> : null}
        </form>
        <div className="mt-4 border-t border-slate-200 pt-3">
          <h3 className="text-xs font-bold uppercase tracking-wide text-slate-600">Your recent reports</h3>
          {reports.length ? <ul className="mt-2 space-y-2">{reports.map((report) => <li key={report.id} className="rounded-lg border border-slate-200 p-2 text-xs">
            <div className="flex items-center justify-between gap-2"><strong>{CATEGORIES.find(([value]) => value === report.category)?.[1] || 'Hazard report'}</strong><span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 font-semibold">{COMMUNITY_REPORTS_ENHANCED ? citizenReportStatusLabel(report.status) : STATUS_LABELS[report.status] || report.status || 'Pending'}</span></div>
            <p className="mt-1 text-slate-600">{report.description}</p><time className="mt-1 block text-slate-500">{reportDate(report.submitted_at)}</time>
          </li>)}</ul> : reportsLoadStatus === 'success' ? <p className="mt-2 text-xs text-slate-500">No reports submitted yet.</p> : reportsLoadStatus === 'error' ? <p role="alert" className="mt-2 text-xs text-rose-700">Your reports could not be loaded.</p> : <p role="status" className="mt-2 text-xs text-slate-500">Loading your reports...</p>}
        </div>
      </div>
      {COMMUNITY_REPORTS_ENHANCED ? <div className="space-y-2">
        <div>
          <label htmlFor="community-report-place" className="block text-xs font-semibold text-slate-700">Search place</label>
          <input id="community-report-place" type="search" autoComplete="off" value={searchQuery} onChange={(event) => { selectedPlaceLabelRef.current = ''; setSelectedLocation({ valid: false, placeName: '' }); setForm((current) => ({ ...current, latitude: '', longitude: '' })); setSearchQuery(event.target.value) }} aria-autocomplete="list" aria-expanded={suggestions.length > 0} aria-controls="community-report-place-suggestions" className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Search a Karnataka place, e.g. Madikeri" />
          {suggestions.length ? <ul id="community-report-place-suggestions" role="listbox" className="mt-1 max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-sm">{suggestions.map((place) => <li key={`${place.latitude}-${place.longitude}`} role="option" aria-selected="false"><button type="button" onClick={() => applyPlace(place)} className="w-full px-3 py-2 text-left text-sm hover:bg-emerald-50">{place.label}</button></li>)}</ul> : null}
          {searchLoading ? <p role="status" className="mt-1 text-xs text-slate-500">Searching Karnataka...</p> : null}
          {!suggestions.length && !searchLoading && !searchError && searchQuery.trim().length >= 3 && searchQuery !== selectedPlaceLabelRef.current ? <p role="status" className="mt-1 text-xs text-slate-500">No places found</p> : null}
          {searchError ? <p role="status" className="mt-1 text-xs text-amber-800">{searchError}</p> : null}
        </div>
        <button type="button" onClick={useCurrentLocation} className="rounded-lg border border-emerald-800 px-3 py-2 text-xs font-semibold text-emerald-900">Use my current location</button>
        {selectedLocation.valid ? <p className="text-xs font-semibold text-emerald-800">Selected: {selectedLocation.label}</p> : selectedLocation.checking ? <p role="status" className="text-xs text-slate-500">Checking selected location...</p> : null}
        <CommunityReportLocationMap location={selectedLocation} onLocationChange={chooseCoordinates} />
      </div> : null}
    </div>
  </section>
}

export function AdminCommunityReports({ token }) {
  const [reports, setReports] = useState(EMPTY)
  const [selected, setSelected] = useState(null)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const limit = 20

  const loadReports = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(page * limit) })
      if (statusFilter) params.set('status', statusFilter)
      if (categoryFilter) params.set('category', categoryFilter)
      const response = await apiFetch(`/admin/community-reports?${params}`, {}, token)
      setReports(response.reports || EMPTY)
      setTotal(response.total || 0)
    } catch (err) {
      setError(err?.status === 403 ? 'Administrator access is required.' : 'Reports could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [categoryFilter, page, statusFilter, token])

  useEffect(() => { void loadReports() }, [loadReports])

  async function selectReport(report) {
    setSelected(null)
    setNote('')
    try {
      setSelected(await apiFetch(`/admin/community-reports/${encodeURIComponent(report.id)}`, {}, token))
    } catch {
      setError('Report details could not be loaded.')
    }
  }

  async function review(status) {
    if (!selected?.report) return
    setError('')
    try {
      const result = await apiFetch(`/admin/community-reports/${encodeURIComponent(selected.report.id)}/review`, {
        method: 'POST', body: JSON.stringify({ status, review_note: note }),
      }, token)
      setSelected(result)
      setNote('')
      await loadReports()
    } catch (err) {
      setError(err?.status === 409 ? 'This report has already reached a final status.' : 'Review could not be saved.')
    }
  }

  return <section className="mt-5 rounded-2xl border border-violet-300/20 bg-[#111526] p-5 text-slate-100" aria-labelledby="admin-community-reports-title">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold tracking-[0.2em] text-violet-200">COMMUNITY REPORTS</p><h2 id="admin-community-reports-title" className="mt-1 text-xl font-bold">{COMMUNITY_REPORTS_ENHANCED ? 'Community report review' : 'Report review queue'}</h2><p className="mt-1 text-xs text-slate-400">Citizen reports are separate from official hazard zones and ML risk inputs.</p></div><div className="flex gap-2">
      <select aria-label="Filter reports by status" value={statusFilter} onChange={(event) => { setPage(0); setStatusFilter(event.target.value) }} className="rounded-lg border border-white/15 bg-[#091521] px-2 py-2 text-xs"><option value="">All statuses</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <select aria-label="Filter reports by category" value={categoryFilter} onChange={(event) => { setPage(0); setCategoryFilter(event.target.value) }} className="rounded-lg border border-white/15 bg-[#091521] px-2 py-2 text-xs"><option value="">All categories</option>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
    </div></div>
    {error ? <p role="alert" className="mt-3 text-sm text-rose-200">{error}</p> : null}
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <div className="space-y-2">{loading ? <p className="text-sm text-slate-400">Loading reports…</p> : reports.length ? reports.map((report) => <button type="button" onClick={() => selectReport(report)} key={report.id} className={`block w-full rounded-xl border p-3 text-left ${selected?.report?.id === report.id ? 'border-cyan-200 bg-cyan-300/10' : 'border-white/10 bg-black/10'}`}>
        <div className="flex justify-between gap-2 text-sm"><strong>{CATEGORIES.find(([value]) => value === report.category)?.[1] || report.category}</strong><span>{STATUS_LABELS[report.status] || report.status || 'Pending'}</span></div><p className="mt-1 line-clamp-2 text-xs text-slate-300">{report.description}</p>{COMMUNITY_REPORTS_ENHANCED ? <p className="mt-1 text-[11px] text-slate-400">Reported by: Citizen · Location: {Number(report.latitude).toFixed(4)}, {Number(report.longitude).toFixed(4)}</p> : null}<span className="mt-1 block text-[11px] text-slate-500">{report.id} · {reportDate(report.submitted_at)}</span>
      </button>) : <p className="text-sm text-slate-400">No reports match these filters.</p>}
        <div className="flex items-center justify-between text-xs text-slate-400"><span>{total} reports</span><div className="flex gap-2"><button type="button" disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))} className="rounded border border-white/15 px-2 py-1 disabled:opacity-40">Previous</button><button type="button" disabled={(page + 1) * limit >= total} onClick={() => setPage((current) => current + 1)} className="rounded border border-white/15 px-2 py-1 disabled:opacity-40">Next</button></div></div>
      </div>
      <div className="space-y-3">
        <div className="h-64 overflow-hidden rounded-xl border border-white/10"><MapView zones={EMPTY} communityReports={reports} showRejectedCommunityReports /></div>
        {selected?.report ? <div className="rounded-xl border border-white/10 bg-black/10 p-3">
          <h3 className="font-semibold">Selected report</h3><p className="mt-1 text-xs text-slate-300">{selected.report.latitude}, {selected.report.longitude} · {STATUS_LABELS[selected.report.status] || selected.report.status}</p>{COMMUNITY_REPORTS_ENHANCED ? <p className="mt-1 text-xs text-slate-400">Reported by: Citizen</p> : null}<p className="mt-2 whitespace-pre-wrap text-sm">{selected.report.description}</p>
          <label className="mt-3 block text-xs text-slate-300">Review note<textarea maxLength="1000" rows="2" value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 block w-full rounded-lg border border-white/15 bg-[#091521] px-3 py-2 text-sm text-white" /></label>
          {['pending', 'under_review'].includes(selected.report.status) ? <div className="mt-3 flex flex-wrap gap-2">{selected.report.status === 'pending' ? <button type="button" onClick={() => review('under_review')} className="rounded-lg border border-amber-200/30 px-3 py-2 text-xs">Mark Under Review</button> : null}<button type="button" onClick={() => review('verified')} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold">{COMMUNITY_REPORTS_ENHANCED ? 'Approve' : 'Verify'}</button><button type="button" onClick={() => review('rejected')} className="rounded-lg bg-rose-800 px-3 py-2 text-xs font-semibold">Reject</button></div> : null}
          <h4 className="mt-4 border-t border-white/10 pt-3 text-xs font-bold uppercase tracking-wide">Status history</h4><ol className="mt-2 space-y-2">{(selected.history || []).map((event, index) => <li key={`${event.changed_at}-${index}`} className="text-xs text-slate-300"><strong>{STATUS_LABELS[event.to_status] || event.to_status}</strong> · {event.actor_role}{event.actor_uid ? ` · ${event.actor_uid}` : ''} · {reportDate(event.changed_at)}{event.review_note ? <p className="mt-1">{event.review_note}</p> : null}</li>)}</ol>
        </div> : <p className="text-sm text-slate-400">Choose a report to inspect its location, description, and review history.</p>}
      </div>
    </div>
  </section>
}
