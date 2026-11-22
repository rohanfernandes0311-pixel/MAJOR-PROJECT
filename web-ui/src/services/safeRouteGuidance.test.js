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

test('elevated Citizen warnings expose existing route and safety-guidance actions without auto-routing', async () => {
  const [publicSource, panel] = await Promise.all([readFile(publicUrl, 'utf8'), readFile(panelUrl, 'utf8')])
  assert.match(publicSource, /const elevatedRisk = isEvacuationRisk\(status\.risk\)/)
  assert.match(publicSource, /View safe route/)
  assert.match(publicSource, /Play safety guidance/)
  assert.match(publicSource, /scrollToSection\(routeRef\)/)
  assert.match(panel, /Play safety guidance/)
  assert.match(publicSource, /apiFetch\('\/alerts\/my'/)
  assert.match(publicSource, /alertNotificationManagerRef\.current\.observe\(alerts/)
  assert.match(publicSource, /setInterval\(refreshTargetedAlerts, 60000\)/)
  assert.doesNotMatch(publicSource, /onClick=\{findSaferRoute\}/)
})

test('Citizen hides both cards by role while preserving them for other Public-page roles', async () => {
  const source = await readFile(publicUrl, 'utf8')
  assert.match(source, /const isCitizen = String\(profile\?\.role \|\| ''\)\.trim\(\)\.toLowerCase\(\) === 'citizen'/)
  assert.match(source, /const SHOW_CITIZEN_MODEL_EXPLANATION = false/)
  assert.match(source, /\{!isCitizen \|\| SHOW_CITIZEN_MODEL_EXPLANATION \? \(\s*<section className="border[\s\S]{0,250}Why this model score\?/ )
  assert.match(source, /const SHOW_CITIZEN_RISK_TREND = false/)
  assert.match(source, /\{!isCitizen \|\| SHOW_CITIZEN_RISK_TREND \? <section className="citizen-trend[\s\S]{0,500}Historical risk trend is not available\./)
  assert.match(source, /const SHOW_CITIZEN_RAINFALL_CONTEXT = false/)
  assert.match(source, /authStatus === 'loading' \|\| \(isCitizen && !SHOW_CITIZEN_RAINFALL_CONTEXT\)/)
  assert.match(source, /const RainfallDashboard = lazy\(\(\) => import\('\.\.\/components\/RainfallDashboard'\)\)/)
  assert.match(source, /<Suspense fallback=\{<section aria-label="Rainfall context" aria-busy="true" className="citizen-trend min-h-\[40rem\]/)
  assert.match(source, /<RainfallDashboard trends=\{rainfallTrends\}/)
  assert.match(source, /\{!isCitizen \? \(\s*<section ref=\{alertsRef\}[\s\S]{0,400}Active alerts/)
  assert.match(source, /const refreshTargetedAlerts = useCallback/)
  assert.match(source, /apiFetch\('\/alerts\/my'/)
  assert.match(source, /ref=\{alertControlsRef\} id=\{isCitizen \? 'targeted-alerts' : undefined\}/)
})

test('elevated warning actions remain gated by the existing in-zone risk state', async () => {
  const source = await readFile(publicUrl, 'utf8')
  assert.match(source, /routeGuidanceAvailable = Boolean\(location && activeZoneId && isEvacuationRisk\(status\.risk\)\)/)
  assert.match(source, /elevatedRisk \? \(/)
  assert.match(source, /if \(!isEvacuationRisk\(status\.risk\)\)/)
})
