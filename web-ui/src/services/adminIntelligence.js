import { createCitizenWeatherController, validWeatherLocation } from './citizenWeather.js'
import { createCitizenPrecipitationController } from './citizenPrecipitation.js'

const VALID_SOURCE_STATES = new Set(['REAL', 'SIMULATED', 'UNAVAILABLE'])

export function buildAdminIntelligence(base) {
  if (!base?.zone || !base?.assessment) return null
  const weatherSource = VALID_SOURCE_STATES.has(String(base.weatherSource).toUpperCase())
    ? String(base.weatherSource).toUpperCase()
    : 'UNAVAILABLE'
  return {
    ...base,
    weatherSource,
    overallRisk: base.assessment.overallRisk,
    confidence: base.assessment.confidence,
    confidenceLabel: base.assessment.confidenceLabel,
    factors: Array.isArray(base.assessment.factors) ? base.assessment.factors : [],
    explanations: Array.isArray(base.assessment.explanations) ? base.assessment.explanations : [],
    dataQuality: base.assessment.dataQuality,
    recommendedAction: base.assessment.recommendedAction,
    automaticAlert: base.assessment.automaticAlert,
  }
}

// Display state only. Never changes the backend intelligence or prediction inputs.
export function createAdminLiveEnvironmentController({ request, onChange, ...timing }) {
  let key
  let resetting = false
  let disposed = false
  let state = {}
  const publish = (changes) => {
    if (resetting || disposed) return
    state = { ...state, ...changes }
    onChange(state)
  }
  const weather = createCitizenWeatherController({
    ...timing,
    request: (latitude, longitude, signal) => request(`/citizen/weather/current?latitude=${latitude}&longitude=${longitude}`, { signal, cache: 'no-store' }),
    onChange: ({ weather, loading, error }) => publish({ weather, weatherLoading: loading, weatherError: error }),
  })
  const precipitation = createCitizenPrecipitationController({
    ...timing,
    request: (latitude, longitude, signal) => request(`/citizen/environment/precipitation?latitude=${latitude}&longitude=${longitude}`, { signal, cache: 'no-store' }),
    onChange: ({ observation, loading }) => publish({ precipitation: observation, precipitationLoading: loading }),
  })
  return {
    setZone(zone) {
      if (disposed) return
      const location = { lat: zone?.latitude, lng: zone?.longitude }
      const valid = Boolean(zone?.zone_id) && validWeatherLocation(location)
      const nextKey = JSON.stringify([zone?.zone_id ?? null, location.lat ?? null, location.lng ?? null])
      if (nextKey === key) return
      key = nextKey
      // Reset both controllers even for nearby zones: no old-zone response or
      // measurement survives a selection change. Their request limits remain.
      resetting = true
      weather.setLocation(null)
      precipitation.setLocation(null)
      resetting = false
      state = {
        zoneId: zone?.zone_id ?? null,
        latitude: location.lat ?? null,
        longitude: location.lng ?? null,
        weather: null, weatherLoading: valid, weatherError: '',
        precipitation: null, precipitationLoading: valid,
      }
      onChange(state)
      if (valid) {
        weather.setLocation(location)
        precipitation.setLocation(location)
      }
    },
    dispose() {
      disposed = true
      weather.dispose()
      precipitation.dispose()
    },
  }
}
