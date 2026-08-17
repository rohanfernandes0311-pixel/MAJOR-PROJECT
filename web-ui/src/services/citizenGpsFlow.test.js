import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('Citizen uses one live GPS watcher, cleans it up, and reports permission and availability failures', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /navigator\.geolocation\.watchPosition\(/)
  assert.match(source, /navigator\.geolocation\.clearWatch\(locationWatchId\)/)
  assert.match(source, /Live geofencing cannot operate while location access is denied/)
  assert.match(source, /Unable to determine your current location/)
  assert.doesNotMatch(source, /navigator\.geolocation\.getCurrentPosition\(/)
})

test('Citizen geofencing uses actual GPS prediction matches and never simulation-adjusted risk', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /prediction = await tryPredict\(lat, lng\)/)
  assert.match(source, /deriveCitizenGeofenceState\(prediction\)/)
  assert.match(source, /userLocation=\{location\}/)
  assert.match(source, /selectedZone=\{zones\.find/)
  assert.doesNotMatch(source, /locationUpdate\?\.final_risk/)
  assert.doesNotMatch(source, /simulationState|setSimulationState/)
  assert.doesNotMatch(source, /SIMULATION MODE ACTIVE|Emergency drill panel/)
})

test('Citizen alerts are deduplicated by configured zone and risk', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /notificationKey = `\$\{geofence\.activeZoneId\}:\$\{geofence\.rawRisk\}`/)
  assert.match(source, /lastNotifiedZoneRiskRef\.current !== notificationKey/)
})
