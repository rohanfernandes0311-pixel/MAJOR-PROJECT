import scenarios from './incidentScenarios.json' with { type: 'json' }

// Curated presentation data only. These records are not a live incident feed,
// configured geofences, or inputs to real recipient targeting. The backend
// reads the same catalog for Admin explainability, so provenance cannot drift.
export const INCIDENT_SCENARIO_LABEL = 'REAL-WORLD INCIDENT / DEMO SCENARIO'
export const INCIDENT_SCENARIOS = Object.freeze(scenarios.map((scenario) => Object.freeze(scenario)))

export function getIncidentScenario(id) {
  return INCIDENT_SCENARIOS.find((scenario) => scenario.id === String(id || '')) || null
}
