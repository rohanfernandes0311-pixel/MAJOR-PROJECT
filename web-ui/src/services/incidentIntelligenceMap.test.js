import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('configured-zone analysis synchronizes map, intelligence, population, and matched incident context', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /const contextualMapIncident = selectedConfiguredZone \? zoneIntelligence\?\.recentIncident/)
  assert.match(source, /const mapIncident = activeMapIncident \|\| contextualMapIncident/)
  assert.match(source, /const incidentDemoMode = Boolean\(activeMapIncident\)/)
  assert.match(source, /const mapContext = useMemo/)
  assert.match(source, /insideUsers: zoneIntelligence\?\.affected\?\.insideUsers/)
  assert.match(source, /recipientCount: zoneIntelligence\?\.affected\?\.recipientCount/)
  assert.match(source, /incidentLocation=\{mapIncidentLocation\}/)
  assert.match(source, /mapContext=\{mapContext\}/)
})

test('configured and explicit incident-demo modes preserve their polygon boundary', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /features: incidentMode \? \[\] : zones/)
  assert.match(source, /if \(!incidentMode\) zones\.forEach/)
  assert.match(source, /if \(incidentMode\) map\.setView/)
  assert.match(source, /map\.fitBounds\(selectedBounds/)
  assert.match(source, /L\.circle\(\[incidentLocation\.lat, incidentLocation\.lng\]/)
  assert.doesNotMatch(source, /L\.rectangle\(/)
})

test('incident popup preserves approximate context and demo classification without exact coordinate claims', async () => {
  const admin = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  const map = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(admin, /location_precision \|\| 'approximate'/)
  assert.match(map, /RECENT INCIDENT · DEMO CONTEXT/)
  assert.match(map, /Classification:/)
  assert.match(map, /Location:/)
  assert.doesNotMatch(map, /incidentLocation\.lat\)\.toFixed/)
  assert.doesNotMatch(map, /incidentLocation\.lng\)\.toFixed/)
})

test('map legend and markers distinguish every operational data class without PII', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  for (const label of ['MAP LEGEND', 'CONFIGURED · Risk zone', 'RECENT', 'Circular affected area', 'REAL · User inside zone', 'REAL · User outside zone', 'SIMULATED · Demo citizen', 'HISTORICAL · Landslide inventory', 'TARGETED · Eligible recipient']) {
    assert.match(source, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'))
  }
  assert.match(source, /recipientEligible \? '#38bdf8'/)
  assert.doesNotMatch(source, /recipient\?\.phone_masked|recipient\?\.user_id/)
})

test('historical marker rendering remains bounded and non-alerting', async () => {
  const map = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  const admin = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(map, /landslideRecords\.slice\(0, 2000\)\.forEach/)
  assert.match(admin, /\/landslides\?limit=2000/)
  assert.doesNotMatch(map, /activateTargetedAlert|send_sms|Twilio/)
})

test('Citizen page remains free of Admin intelligence map layers', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /affectedUserLocations|mapContext|incidentMode|MAP LEGEND/)
})
