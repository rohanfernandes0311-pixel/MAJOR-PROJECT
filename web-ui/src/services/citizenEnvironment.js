export const ENVIRONMENT_UNAVAILABLE = 'Live data unavailable.'
const REFRESH_MS = 30 * 60 * 1000
const MIN_REQUEST_MS = 60 * 1000

function validLocation(value) {
  return value && Number.isFinite(value.lat) && Number.isFinite(value.lng)
    && Math.abs(value.lat) <= 90 && Math.abs(value.lng) <= 180
}

function distanceKm(a, b) {
  const rad = Math.PI / 180
  const h = Math.sin((b.lat - a.lat) * rad / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin((b.lng - a.lng) * rad / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}

export function validSoilObservation(value, now = Date.now()) {
  const timestamp = Date.parse(value?.observed_at)
  return value?.source === 'NASA SMAP NRT' && value.unit === '% water by volume'
    && Number.isFinite(value.soil_moisture_percent) && value.soil_moisture_percent >= 2 && value.soil_moisture_percent <= 50
    && [0, 8].includes(value.retrieval_qual_flag) && [0, 128].includes(value.surface_flag)
    && Number.isFinite(timestamp) && timestamp <= now + 5 * 60 * 1000 && now - timestamp <= 72 * 60 * 60 * 1000
    && Number.isFinite(value.distance_km) && value.distance_km >= 0 && value.distance_km <= 75
    && value.spatial_resolution_km === 36
}

// Consumes Public's existing location state; never owns a browser GPS watcher.
export function createCitizenEnvironmentController({ request, onChange, now = Date.now, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let location = null
  let requested = null
  let started = null
  let timer = null
  let abort = null
  let generation = 0
  let disposed = false
  let inFlight = false

  function clearScheduled() {
    if (timer !== null) clearTimer(timer)
    timer = null
  }
  function invalidate() {
    generation += 1
    abort?.abort()
    abort = null
    inFlight = false
  }
  function schedule(delay) {
    clearScheduled()
    timer = setTimer(() => { timer = null; refresh() }, delay)
  }
  function moved() { return requested && distanceKm(requested, location) >= 5 }
  function refresh() {
    if (disposed || !location || inFlight) return
    const elapsed = started === null ? Infinity : now() - started
    const interval = moved() || !requested ? MIN_REQUEST_MS : REFRESH_MS
    if (elapsed < interval) { schedule(interval - elapsed); return }
    clearScheduled()
    invalidate()
    const current = generation
    requested = { ...location }
    const coordinates = requested
    started = now()
    inFlight = true
    abort = new AbortController()
    const signal = abort.signal
    onChange({ observation: null, loading: true })
    Promise.resolve().then(() => {
      if (disposed || current !== generation) return null
      return request(coordinates.lat, coordinates.lng, signal)
    }).then(observation => {
      if (disposed || current !== generation) return
      if (!validSoilObservation(observation, now())) throw new Error(ENVIRONMENT_UNAVAILABLE)
      onChange({ observation, loading: false })
    }).catch(() => {
      if (!disposed && current === generation) onChange({ observation: null, loading: false })
    }).finally(() => {
      if (disposed || current !== generation) return
      inFlight = false
      abort = null
      schedule(REFRESH_MS)
    })
  }
  return {
    setLocation(value) {
      if (disposed) return
      if (!validLocation(value)) {
        location = null
        requested = null
        clearScheduled()
        invalidate()
        onChange({ observation: null, loading: false })
        return
      }
      location = { lat: value.lat, lng: value.lng }
      if (moved()) { invalidate(); onChange({ observation: null, loading: false }) }
      refresh()
    },
    dispose() { disposed = true; clearScheduled(); invalidate() },
  }
}
