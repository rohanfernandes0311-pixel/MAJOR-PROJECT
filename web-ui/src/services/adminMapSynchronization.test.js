import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('Admin incident map state requires active simulation and valid scenario coordinates', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /if \(!simulation\.enabled \|\| !selectedIncident\) return null/)
  assert.match(source, /Number\(selectedIncident\.latitude\)/)
  assert.match(source, /Number\(selectedIncident\.longitude\)/)
  assert.match(source, /Number\.isFinite\(latitude\) && Number\.isFinite\(longitude\)/)
})

test('current Admin controls key and populate the map without a page reload', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /const adminMapKey = \[/)
  assert.match(source, /selectedConfiguredZone \|\| 'no-configured-zone'/)
  assert.match(source, /activeMapIncident\?\.id \|\| 'no-incident'/)
  assert.match(source, /key=\{adminMapKey\}/)
  assert.match(source, /simulatedLocation=\{activeMapIncident \? null : simulationLocation\}/)
  assert.match(source, /lat: activeMapIncident\.latitude/)
  assert.match(source, /lng: activeMapIncident\.longitude/)
  assert.match(source, /simulation=\{simulation\.enabled\}/)
  assert.doesNotMatch(source, /window\.location\.reload/)
})

test('configured selection passes existing geometry, risk, and duration to the map', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /selectedZone=\{selectedConfiguredZoneGeometry\}/)
  assert.match(source, /selectedZoneRisk=\{affectedRisk\}/)
  assert.match(source, /selectedZoneDuration=\{affectedDuration\}/)
})

test('simulated incident and configured-zone popups expose only presentation data', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /<b>SIMULATED INCIDENT<\/b>/)
  assert.match(source, /Status:.*Active simulation/)
  assert.match(source, /Latitude:/)
  assert.match(source, /Longitude:/)
  assert.match(source, /<b>Configured Risk Zone<\/b>/)
  assert.match(source, /selectedZoneDuration/)
  assert.doesNotMatch(source, /JWT|Firebase|password/i)
})
