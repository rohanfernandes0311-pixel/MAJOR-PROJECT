export const WEATHER_UNAVAILABLE = 'Live weather unavailable.'
const REFRESH_MS = 5 * 60 * 1000
const MIN_REQUEST_MS = 60 * 1000
const MOVEMENT_KM = 1

export function validWeatherLocation(location) {
  return location != null && Number.isFinite(location.lat) && Number.isFinite(location.lng)
    && Math.abs(location.lat) <= 90 && Math.abs(location.lng) <= 180
}

function distanceKm(a, b) {
  const radians = value => value * Math.PI / 180
  const dLat = radians(b.lat - a.lat)
  const dLng = radians(b.lng - a.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(a.lat)) * Math.cos(radians(b.lat)) * Math.sin(dLng / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}

export function weatherFields(weather) {
  const measurement = (value, unit, digits = 1) => Number.isFinite(value)
    ? `${value.toFixed(digits)} ${unit}` : 'Unavailable'
  const observed = weather?.observed_at ? new Date(weather.observed_at) : null
  return [
    { label: 'Temperature', value: measurement(weather?.temperature_c, '°C') },
    { label: 'Weather', value: typeof weather?.description === 'string' && weather.description.trim() ? weather.description : 'Unavailable' },
    { label: 'Humidity', value: measurement(weather?.humidity_pct, '%', 0) },
    { label: 'Wind speed', value: measurement(weather?.wind_speed_mps, 'm/s') },
    { label: 'Visibility', value: measurement(weather?.visibility_km, 'km') },
    { label: 'Precipitation', value: measurement(weather?.precipitation_mm_per_hour, 'mm/h') },
    { label: 'Observed', value: observed && Number.isFinite(observed.getTime()) ? observed.toLocaleString() : 'Unavailable' },
  ]
}

// This controller owns only weather. It consumes the existing location watcher.
export function createCitizenWeatherController({ request, onChange, now = Date.now, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let location = null
  let requestedLocation = null
  let lastStarted = null
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

  function moved() {
    return requestedLocation && distanceKm(requestedLocation, location) >= MOVEMENT_KM
  }

  function schedule(delay) {
    clearScheduled()
    timer = setTimer(() => { timer = null; refresh() }, delay)
  }

  function refresh() {
    if (disposed || !location || inFlight) return
    const elapsed = lastStarted === null ? Infinity : now() - lastStarted
    const dueAfter = moved() || !requestedLocation ? MIN_REQUEST_MS : REFRESH_MS
    if (elapsed < dueAfter) {
      schedule(dueAfter - elapsed)
      return
    }
    invalidate()
    const currentGeneration = generation
    abort = new AbortController()
    const signal = abort.signal
    requestedLocation = { ...location }
    const coordinates = requestedLocation
    lastStarted = now()
    inFlight = true
    onChange({ weather: null, loading: true, error: '' })
    Promise.resolve().then(() => {
      if (disposed || currentGeneration !== generation) return null
      return request(coordinates.lat, coordinates.lng, signal)
    }).then(weather => {
      if (disposed || currentGeneration !== generation) return
      if (!weather || weather.source !== 'weatherbit') throw new Error(WEATHER_UNAVAILABLE)
      onChange({ weather, loading: false, error: '' })
    }).catch(() => {
      if (!disposed && currentGeneration === generation) onChange({ weather: null, loading: false, error: WEATHER_UNAVAILABLE })
    }).finally(() => {
      if (disposed || currentGeneration !== generation) return
      inFlight = false
      abort = null
      schedule(REFRESH_MS)
    })
  }

  return {
    setLocation(value) {
      if (disposed) return
      if (!validWeatherLocation(value)) {
        location = null
        requestedLocation = null
        clearScheduled()
        invalidate()
        onChange({ weather: null, loading: false, error: WEATHER_UNAVAILABLE })
        return
      }
      location = { lat: value.lat, lng: value.lng }
      if (moved()) {
        invalidate()
        onChange({ weather: null, loading: false, error: '' })
      }
      refresh()
    },
    dispose() {
      disposed = true
      clearScheduled()
      invalidate()
    },
  }
}
