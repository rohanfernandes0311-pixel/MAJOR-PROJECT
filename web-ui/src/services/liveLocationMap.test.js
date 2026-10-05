import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('Citizen passes actual GPS accuracy and status through existing location state', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /currentLocation = \{ lat, lng, accuracy \}/)
  assert.match(source, /setLocation\(\{ lat, lng, accuracy \}\)/)
  assert.match(source, /userLocation=\{location\}/)
  assert.match(source, /userLocationStatus=\{locationStatus\}/)
})

test('live marker uses actual accuracy, blue styling, and a non-sensitive location popup', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /radius: Math\.max\(accuracy, 1\)/)
  assert.match(source, /fillColor: '#0ea5e9'/)
  assert.match(source, /🔵 YOU ARE HERE/)
  assert.match(source, /<b>Your Location<\/b>/)
  assert.match(source, /Latitude:/)
  assert.match(source, /Longitude:/)
  assert.match(source, /Accuracy:/)
  assert.doesNotMatch(source, /JWT|Firebase|token/i)
})

test('GPS updates replace only the user layer and center only once', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.equal((source.match(/L\.map\(/g) || []).length, 1)
  assert.match(source, /userLocationLayerRef\.current\?\.remove/)
  assert.match(source, /hasCenteredOnUserRef\.current/)
  assert.match(source, /\}, \[userLocation, userLocationStatus\]\)/)
  const mapLifecycleDependencies = source.match(/\}, \[zones, simulatedLocation[^\n]+landslideRecords, simulationSafeZone, adminSimulationActor\]\)/)?.[0] || ''
  assert.ok(mapLifecycleDependencies)
  assert.doesNotMatch(mapLifecycleDependencies, /userLocation/)
})

test('Leaflet initialization uses the latest GPS fix when location arrives before the map is ready', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /latestUserLocationRef\.current = userLocation/)
  assert.match(source, /latestUserLocationStatusRef\.current = userLocationStatus/)
  assert.match(source, /const currentUserLocation = latestUserLocationRef\.current/)
  assert.match(source, /renderUserLocationLayer\([\s\S]*currentUserLocation,[\s\S]*latestUserLocationStatusRef\.current/)
  assert.match(source, /if\(cancelled \|\| !ref\.current\) return/)
  assert.match(source, /map\.setView\(\[currentUserLocation\.lat, currentUserLocation\.lng\], 15/)
  assert.match(source, /hasValidUserLocation \? [\s\S]*REAL · GPS location/)
})

test('configured GeoJSON geofences retain severity styling and expose zone popups', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /features: incidentMode \? \[\] : zones/)
  assert.match(source, /getFeatureStyle\(feature, currentRiskStyle\)/)
  assert.match(source, /<b>LandSense Risk Zone<\/b>/)
  assert.match(source, /Risk Level:/)
})
