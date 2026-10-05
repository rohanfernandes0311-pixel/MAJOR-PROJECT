import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentUrl = new URL('../components/AdminKodaguSimulation.jsx', import.meta.url)
const adminUrl = new URL('../pages/Admin.jsx', import.meta.url)

test('Kodagu simulation is additive, admin-scoped, and exposes only the five approved locations', async () => {
  const [component, admin] = await Promise.all([readFile(componentUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(admin, /<AdminKodaguSimulation token=\{token\}/)
  assert.match(component, /'Madikeri', 'Virajpet', 'Chittalli', 'Perumbadi', 'Makutta'/)
  for (const excluded of ['Siddapura', 'Murnad', 'Ponnampet', 'Gonnikoppal']) assert.doesNotMatch(component, new RegExp(excluded))
  assert.match(component, /SIMULATION MODE — DEMONSTRATION ONLY/)
  assert.match(component, /\['HIGH', 'CRITICAL'\]/)
})

test('simulation map layers are optional, admin-gated, styled distinctly, and reset with state', async () => {
  const [map, admin, publicPage, component] = await Promise.all([
    readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8'),
    readFile(adminUrl, 'utf8'),
    readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8'),
    readFile(componentUrl, 'utf8')
  ])
  assert.match(map, /simulationRoute = null, showSimulationLayers = false/)
  assert.match(map, /if \(showSimulationLayers && syntheticZone\?\.geometry\)/)
  assert.match(map, /showSimulationLayers && simulationRoute\?\.route\?\.status === 'ok'/)
  assert.match(map, /color: '#22c55e'[\s\S]*weight: 6/)
  assert.match(map, /Simulated Safer Evacuation Route/)
  assert.match(map, /const simulationCenter = getCenterFromFeature\(syntheticZone\)/)
  assert.match(map, /Simulation Location —/)
  assert.match(map, /📍 Simulation Location/)
  assert.match(admin, /showSimulationLayers=\{String\(profile\?\.role \|\| ''\)\.toLowerCase\(\) === 'admin' && simulation\.enabled && simulation\.is_simulation\}/)
  assert.match(admin, /Simulation map geometry unavailable\. No verified project geometry exists for this location\./)
  assert.doesNotMatch(publicPage, /showSimulationLayers|simulationRoute|syntheticZone/)
  assert.match(component, /setScenario\(null\)/)
  assert.doesNotMatch(component, /onStateChange\(|\/kodagu\/(create|reset|trigger)/)
  assert.match(component, /setSelectedRecipientIds\(\[\]\)/)
})

test('recipient selection and preview remain explicit and Excel-only', async () => {
  const component = await readFile(componentUrl, 'utf8')
  assert.match(component, /Select All Eligible/)
  assert.match(component, /Clear Selection/)
  assert.match(component, /checked=\{selectedRecipientIds\.includes/)
  assert.match(component, /disabled=\{!person\.recipientEligible\}/)
  assert.match(component, /\/admin\/simulation\/demo\?location=/)
  assert.match(component, /\/admin\/simulation\/visual\/recipients/)
  assert.match(component, /It does not send SMS/)
})
