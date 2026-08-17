export const INCIDENT_DEMO_STORAGE_KEY = 'landsense_incident_demo_alert'
export const INCIDENT_DEMO_EVENT = 'landsense:incident-demo-alert'

const EARTH_RADIUS_METERS = 6371000

export function distanceMeters(a, b) {
  const radians = (value) => Number(value) * Math.PI / 180
  const dLat = radians(Number(b.latitude) - Number(a.latitude))
  const dLng = radians(Number(b.longitude) - Number(a.longitude))
  const lat1 = radians(a.latitude)
  const lat2 = radians(b.latitude)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(h))
}

function offsetPoint(incident, distance, angle) {
  const north = Math.cos(angle) * distance
  const east = Math.sin(angle) * distance
  return {
    latitude: Number(incident.latitude) + north / 111320,
    longitude: Number(incident.longitude) + east / (111320 * Math.cos(Number(incident.latitude) * Math.PI / 180))
  }
}

export function generateSimulatedCitizens(incident, insideCount = 12, outsideCount = 3) {
  if (!incident) return []
  const inside = Math.max(0, Math.min(50, Number(insideCount) || 0))
  const outside = Math.max(0, Math.min(50, Number(outsideCount) || 0))
  const citizens = []
  for (let index = 0; index < inside + outside; index += 1) {
    const expectedInside = index < inside
    const localIndex = expectedInside ? index : index - inside
    const count = expectedInside ? Math.max(inside, 1) : Math.max(outside, 1)
    const angle = (Math.PI * 2 * localIndex / count) + 0.35
    const radiusFactor = expectedInside ? 0.25 + (localIndex % 5) * 0.12 : 1.25 + (localIndex % 4) * 0.18
    const point = offsetPoint(incident, incident.affected_radius_meters * radiusFactor, angle)
    citizens.push({ id: `SIM-${String(index + 1).padStart(3, '0')}`, ...point, simulated: true })
  }
  return citizens
}

export function previewSimulatedRecipients(incident, citizens) {
  const evaluated = (Array.isArray(citizens) ? citizens : []).map((citizen) => ({
    ...citizen, inside: distanceMeters(incident, citizen) <= Number(incident?.affected_radius_meters || 0)
  }))
  return { citizens: evaluated, total_count: evaluated.length, inside_count: evaluated.filter((item) => item.inside).length, outside_count: evaluated.filter((item) => !item.inside).length }
}

export function formatIncidentDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`)
  return Number.isNaN(date.getTime()) ? String(dateValue || '') : date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
}

export function impactLines(incident) {
  const lines = []
  if (incident?.deaths !== null && incident?.deaths !== undefined) lines.push(`${incident.deaths} ${incident.deaths === 1 ? 'fatality' : 'fatalities'}`)
  if (incident?.injured !== null && incident?.injured !== undefined) lines.push(`${incident.injured} injured`)
  if (incident?.missing !== null && incident?.missing !== undefined && incident.missing > 0) lines.push(`${incident.missing} missing`)
  if (incident?.affected_people !== null && incident?.affected_people !== undefined) lines.push(`${incident.affected_people} people affected`)
  return lines
}

export function buildDemoAlert(incident, preview, launchedAt = new Date().toISOString()) {
  return {
    id: `demo-${incident.id}-${launchedAt}`, simulation: true, title: incident.title, date: incident.date,
    state: incident.state, district: incident.district, location_name: incident.location_name,
    latitude: incident.latitude, longitude: incident.longitude, location_precision: incident.location_precision,
    deaths: incident.deaths, injured: incident.injured, missing: incident.missing, affected_people: incident.affected_people,
    short_description: incident.short_description, demo_risk: incident.demo_risk,
    affected_radius_meters: incident.affected_radius_meters, simulated_citizens: preview.citizens,
    simulated_recipient_count: preview.inside_count, launched_at: launchedAt,
    safety_guidance: 'Stay away from unstable slopes and follow official local guidance.',
    notification_message: `${incident.title}\nAffected area: ${incident.location_name}, ${incident.district}\nSIMULATION — NO REAL ALERT SENT`
  }
}

export function saveDemoAlert(alert, storage = globalThis.localStorage, eventTarget = globalThis.window) {
  storage?.setItem(INCIDENT_DEMO_STORAGE_KEY, JSON.stringify(alert))
  if (typeof CustomEvent !== 'undefined') eventTarget?.dispatchEvent?.(new CustomEvent(INCIDENT_DEMO_EVENT, { detail: alert }))
  return alert
}

export function readDemoAlert(storage = globalThis.localStorage) {
  try {
    const parsed = JSON.parse(storage?.getItem(INCIDENT_DEMO_STORAGE_KEY) || 'null')
    return parsed?.simulation === true ? parsed : null
  } catch { return null }
}

export function clearDemoAlert(storage = globalThis.localStorage, eventTarget = globalThis.window) {
  storage?.removeItem(INCIDENT_DEMO_STORAGE_KEY)
  if (typeof CustomEvent !== 'undefined') eventTarget?.dispatchEvent?.(new CustomEvent(INCIDENT_DEMO_EVENT, { detail: null }))
}

export function buildSimulatedSms(incident) {
  return `LANDSENSE ALERT\n\nLandslide reported near ${incident.location_name}, ${incident.district}.\n\n${incident.short_description}\n\nPlease avoid the affected area and follow official emergency guidance.\n\n[SIMULATION — NOT SENT]`
}
