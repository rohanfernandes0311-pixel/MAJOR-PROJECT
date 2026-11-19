import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { INCIDENT_SCENARIO_LABEL, INCIDENT_SCENARIOS, getIncidentScenario } from '../data/incidentScenarios.js'
import { buildDemoAlert, distanceMeters, generateSimulatedCitizens, previewSimulatedRecipients } from './incidentDemo.js'

const REQUIRED_FIELDS = [
  'id', 'title', 'date', 'state', 'district', 'location_name', 'latitude', 'longitude',
  'location_precision', 'deaths', 'injured', 'missing', 'affected_people', 'short_description',
  'demo_risk', 'affected_radius_meters', 'source_label', 'source_url', 'verification_status'
]

test('curated catalog uses the required provenance schema and conservative unknown values', () => {
  assert.equal(INCIDENT_SCENARIO_LABEL, 'REAL-WORLD INCIDENT / DEMO SCENARIO')
  assert.equal(INCIDENT_SCENARIOS.length, 7)
  for (const scenario of INCIDENT_SCENARIOS) {
    for (const field of REQUIRED_FIELDS) assert.ok(Object.hasOwn(scenario, field), `${scenario.id} missing ${field}`)
    assert.equal(scenario.location_precision, 'approximate')
    assert.match(scenario.source_url, /^https:\/\//)
  }
  assert.equal(getIncidentScenario('wayanad-kalladi-2026-07-07').deaths, 8)
  assert.equal(getIncidentScenario('mumbai-ghatkopar-2026-08-12').injured, 4)
  assert.equal(getIncidentScenario('mumbai-kurla-2026-08').deaths, null)
  assert.equal(getIncidentScenario('mumbai-kurla-2026-08').verification_status, 'source_review_required')
})

test('simulated citizens are deterministically separated by the affected radius', () => {
  const incident = getIncidentScenario('wayanad-kalladi-2026-07-07')
  const citizens = generateSimulatedCitizens(incident, 12, 3)
  const preview = previewSimulatedRecipients(incident, citizens)

  assert.equal(preview.total_count, 15)
  assert.equal(preview.inside_count, 12)
  assert.equal(preview.outside_count, 3)
  assert.ok(preview.citizens.filter((item) => item.inside).every((item) => distanceMeters(incident, item) <= incident.affected_radius_meters))
  assert.ok(preview.citizens.filter((item) => !item.inside).every((item) => distanceMeters(incident, item) > incident.affected_radius_meters))
})

test('demo alert contains citizen-readable fields but no source, provider, phone, or delivery internals', () => {
  const incident = getIncidentScenario('wayanad-kalladi-2026-07-07')
  const preview = previewSimulatedRecipients(incident, generateSimulatedCitizens(incident, 2, 1))
  const alert = buildDemoAlert(incident, preview, '2026-08-15T12:00:00Z')

  assert.equal(alert.simulated_recipient_count, 2)
  assert.equal(alert.simulation, true)
  assert.match(alert.notification_message, /SIMULATION — NO REAL ALERT SENT/)
  for (const forbidden of ['source_label', 'source_url', 'provider', 'phone', 'delivery_status', 'user_id']) {
    assert.equal(Object.hasOwn(alert, forbidden), false)
  }
})

test('admin uses separate configured and incident state and demo launch has no network path', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /selectedConfiguredZone, setSelectedConfiguredZone/)
  assert.match(source, /selectedIncidentScenario, setSelectedIncidentScenario/)
  assert.match(source, /A\. CONFIGURED ALERT ZONES/)
  assert.match(source, /B\. RECENT \/ HISTORICAL INCIDENT DEMO SCENARIOS/)
  assert.match(source, /apiFetch\('\/zones', \{\}, token\)/)
  assert.match(source, /apiFetch\('\/admin\/affected-zones\/preview'/)
  assert.match(source, /apiFetch\('\/admin\/affected-zones\/activate'/)

  const launchBody = source.match(/function launchDemoAlert\(\) \{([\s\S]*?)\n  \}/)?.[1] || ''
  assert.match(launchBody, /buildDemoAlert/)
  assert.match(launchBody, /saveDemoAlert/)
  assert.doesNotMatch(launchBody, /apiFetch|fetch\(|Twilio|location-update/)
})

test('map keeps real GPS, simulated citizens, incident marker, and affected area distinct', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /userLocation = null, userLocationStatus = '', simulatedLocation = null, simulatedCitizens = EMPTY_LAYERS, incidentLocation = null/)
  assert.match(source, /bindTooltip\('🔵 YOU ARE HERE'/)
  assert.match(source, /SIMULATED CITIZEN/)
  assert.match(source, /circular affected area/)
  assert.match(source, /map\.setView\(\[incidentLocation\.lat, incidentLocation\.lng\]/)
  assert.match(source, /radius: Number\(incidentRadiusMeters\)/)
  assert.match(source, /features: incidentMode \? \[\] : zones/)
  assert.doesNotMatch(source, /L\.rectangle\(/)

  const citizen = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(citizen, /userLocation=\{location\}/)
  assert.doesNotMatch(citizen, /incidentLocation=\{demoAlert/)
  assert.doesNotMatch(citizen, /simulatedCitizens=\{demoAlert/)
  assert.doesNotMatch(citizen, /setLocation\(.*demoAlert/)
})

test('noncitizen Public alert inbox remains human-readable and hides delivery internals', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /\{!isCitizen \? \(\s*<section ref=\{alertsRef\}/)
  assert.match(source, /LANDSLIDE ALERT/)
  assert.match(source, /SIMULATION.*NOT A LIVE ALERT/)
  assert.match(source, /demoAlert\.safety_guidance/)
  assert.doesNotMatch(source, /Synthetic rainfall estimate/)
  assert.doesNotMatch(source, /Live weather data from/)
  assert.doesNotMatch(source, /alert\.delivery_status/)
})
