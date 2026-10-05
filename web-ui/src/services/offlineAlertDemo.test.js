import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const adminPath = new URL('../pages/Admin.jsx', import.meta.url)
const panelPath = new URL('../components/AdminOfflineAlertDemo.jsx', import.meta.url)
const mapPath = new URL('../shared/MapView.jsx', import.meta.url)
const publicPath = new URL('../pages/Public.jsx', import.meta.url)

test('configured red zones and catalog incident radii are the only clickable offline-demo areas', async () => {
  const map = await readFile(mapPath, 'utf8')
  assert.match(map, /\['HIGH', 'CRITICAL'\]\.includes/)
  assert.match(map, /onRiskAreaSelect\(\{ type: 'configured-zone'/)
  assert.match(map, /onRiskAreaSelect\(\{ type: 'incident'/)
  assert.doesNotMatch(map, /L\.rectangle/)
})

test('admin uses server-calculated recipients and explicit confirmation', async () => {
  const [admin, panel] = await Promise.all([readFile(adminPath, 'utf8'), readFile(panelPath, 'utf8')])
  assert.match(admin, /\/admin\/offline-demo-alerts\/preview/)
  assert.match(admin, /\/admin\/offline-demo-alerts\/send/)
  assert.match(admin, /confirmed: true/)
  assert.match(panel, /Affected registered users/)
  assert.match(panel, /SMS Demo/)
  assert.match(panel, /Bluetooth Demo/)
  assert.match(panel, /Send Offline Demo Alert/)
  assert.match(panel, /NO REAL ALERT WILL BE SENT/)
})

test('demo result is explicit about simulation and zero real delivery', async () => {
  const panel = await readFile(panelPath, 'utf8')
  assert.match(panel, /SIMULATED/)
  assert.match(panel, /Real SMS/)
  assert.match(panel, /Real Bluetooth/)
  assert.match(panel, /Real alerts/)
  assert.match(panel, /No physical transmission occurs/)
  assert.doesNotMatch(panel, /Twilio.*apiFetch|Firebase.*apiFetch/)
})

test('existing citizen inbox receives only the sanitized local demo alert', async () => {
  const [admin, citizen] = await Promise.all([readFile(adminPath, 'utf8'), readFile(publicPath, 'utf8')])
  assert.match(admin, /saveDemoAlert\(result\.demoAlert\)/)
  assert.match(citizen, /demoAlert\.offline_demo/)
  assert.match(citizen, /OFFLINE DEMO · NO REAL MESSAGE WAS SENT/)
  assert.doesNotMatch(citizen, /offline-demo-alerts\/send|Send Offline Demo Alert|Bluetooth Demo checkbox/)
})

test('real activation remains separate and disabled in simulation mode', async () => {
  const admin = await readFile(adminPath, 'utf8')
  assert.match(admin, /apiFetch\('\/admin\/affected-zones\/activate'/)
  assert.match(admin, /if \(!recipientPreview \|\| !affectedZoneId \|\| selectedIncident \|\| simulation\.enabled\) return/)
  assert.match(admin, /disabled=\{activationLoading \|\| simulation\.enabled\}/)
})
