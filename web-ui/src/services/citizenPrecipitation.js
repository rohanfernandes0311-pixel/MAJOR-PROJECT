export const PRECIPITATION_UNAVAILABLE = 'Live data unavailable.'
const REFRESH_MS = 15 * 60 * 1000
const MIN_REQUEST_MS = 60 * 1000

function validLocation(value) {
  return value && Number.isFinite(value.lat) && Number.isFinite(value.lng)
    && Math.abs(value.lat) <= 90 && Math.abs(value.lng) <= 180
}

function cell(value) {
  return `${Math.min(1799, Math.floor((value.lat + 90) * 10))}:${Math.min(3599, Math.floor((value.lng + 180) * 10))}`
}

export function validPrecipitationObservation(value, now = Date.now()) {
  const timestamp = Date.parse(value?.observed_at)
  const end = Date.parse(value?.interval_end)
  return value?.source === 'NASA GPM IMERG Early' && value.unit === 'mm/h'
    && Number.isFinite(value.precipitation_rate) && value.precipitation_rate >= 0 && value.precipitation_rate <= 200
    && Number.isFinite(value.quality_index) && value.quality_index > 0 && value.quality_index <= 1
    && Number.isFinite(value.random_error_mm_h) && value.random_error_mm_h >= 0 && value.random_error_mm_h <= 1000
    && Number.isFinite(timestamp) && timestamp <= now + 5 * 60 * 1000 && now - timestamp <= 12 * 60 * 60 * 1000
    && Number.isFinite(end) && end - timestamp >= 1799000 && end - timestamp <= 1800000
    && value.interval_minutes === 30 && value.spatial_resolution_degrees === 0.1
    && Number.isFinite(value.distance_km) && value.distance_km >= 0 && value.distance_km <= 8
}

// Consumes Public's existing location state; never owns a browser GPS watcher.
export function createCitizenPrecipitationController({ request, onChange, now = Date.now, setTimer = setTimeout, clearTimer = clearTimeout }) {
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
  function moved() { return requested && cell(requested) !== cell(location) }
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
      if (!validPrecipitationObservation(observation, now())) throw new Error(PRECIPITATION_UNAVAILABLE)
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
