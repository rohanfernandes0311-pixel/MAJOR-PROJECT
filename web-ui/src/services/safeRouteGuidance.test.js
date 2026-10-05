import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const publicUrl = new URL('../pages/Public.jsx', import.meta.url)
const panelUrl = new URL('../shared/EvacuationPanel.jsx', import.meta.url)
const mapUrl = new URL('../shared/MapView.jsx', import.meta.url)

test('Safe Route Guidance is gated by current configured-zone HIGH or CRITICAL risk', async () => {
  const [publicSource, panel] = await Promise.all([readFile(publicUrl, 'utf8'), readFile(panelUrl, 'utf8')])
  assert.match(publicSource, /const geofence = deriveCitizenGeofenceState\(prediction\)/)
  assert.match(publicSource, /routeGuidanceAvailable = Boolean\(location && activeZoneId && isEvacuationRisk\(status\.risk\)\)/)
  assert.match(publicSource, /\{routeGuidanceAvailable \? \(/)
  assert.match(panel, /normalizedRisk !== 'HIGH' && normalizedRisk !== 'CRITICAL'/)
  assert.match(panel, /HIGH LANDSLIDE RISK/)
  assert.match(panel, /CRITICAL LANDSLIDE RISK/)
  assert.doesNotMatch(publicSource, /final_risk[\s\S]{0,120}routeGuidanceAvailable/)
})

test('Citizen explicitly enters a destination and requests the existing route-safe endpoint', async () => {
  const [publicSource, panel] = await Promise.all([readFile(publicUrl, 'utf8'), readFile(panelUrl, 'utf8')])
  assert.match(panel, /Destination coordinates/)
  assert.match(panel, /Find Safer Route/)
  assert.match(panel, /onClick=\{onFindRoute\}/)
  assert.match(publicSource, /const findSaferRoute = useCallback/)
  assert.match(publicSource, /fetchJson\('\/route-safe'/)
  assert.match(publicSource, /start_latitude: location\.lat/)
  assert.match(publicSource, /start_longitude: location\.lng/)
  assert.match(publicSource, /end_latitude: destinationLatitude/)
  assert.match(publicSource, /end_longitude: destinationLongitude/)
  assert.doesNotMatch(publicSource, /getSafeZoneCenter|await updateRoute/)
})

test('route request reuses the existing GPS watcher and never auto-routes on position updates', async () => {
  const source = await readFile(publicUrl, 'utf8')
  assert.equal((source.match(/navigator\.geolocation\.watchPosition\(/g) || []).length, 1)
  assert.equal((source.match(/navigator\.geolocation\.clearWatch\(/g) || []).length, 1)
  assert.doesNotMatch(source, /evaluatePosition[\s\S]{0,400}findSaferRoute\(/)
  assert.match(source, /setRoute\(null\)[\s\S]*setRouteError\(''\)/)
})

test('map displays a labeled route line, selected destination, and fitted route bounds', async () => {
  const source = await readFile(mapUrl, 'utf8')
  assert.match(source, /L\.polyline\(routePath/)
  assert.match(source, /Recommended safer route/)
  assert.match(source, /bindTooltip\('Destination'/)
  assert.match(source, /routeLayer\.getBounds\(\)/)
  assert.match(source, /GUIDANCE · Recommended safer route/)
  assert.match(source, /DESTINATION · User selected/)
  assert.doesNotMatch(source, /L\.rectangle/)
})

test('guidance is cautious and never claims absolute safety', async () => {
  const panel = await readFile(panelUrl, 'utf8')
  assert.match(panel, /A safer route is guidance, not a guarantee of safety/)
  assert.match(panel, /follow official instructions/)
  assert.doesNotMatch(panel, /100% safe|completely safe|guaranteed safe/i)
})
