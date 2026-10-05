import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('Admin affected population keeps real and simulated populations separate', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /AFFECTED POPULATION/)
  assert.match(source, /Real users inside/)
  assert.match(source, /Real users outside/)
  assert.match(source, /Real alert recipients/)
  assert.match(source, /Simulated citizens/)
  assert.match(source, /const realAffectedUsers/)
  assert.match(source, /const displayedSimulatedCitizens/)
  assert.match(source, /user\.status/)
  assert.doesNotMatch(source, /const \[affectedUsers, setAffectedUsers\]/)
})

test('preview action remains the existing Phase 5 server workflow and never auto-activates', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /onPreview=\{previewRecipients\}/)
  assert.match(source, /apiFetch\('\/admin\/affected-zones\/preview'/)
  assert.match(source, /Automatic alert: OFF/)
  assert.match(source, /disabled=\{activationLoading \|\| simulation\.enabled\}/)
})

test('map renders distinct real inside, real outside, and simulated citizen markers', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(source, /affectedUserLocations\.forEach/)
  assert.match(source, /inside \? \(simulationSafeZone \? '#ef4444' : '#22c55e'\) : '#94a3b8'/)
  assert.match(source, /REAL · User inside zone/)
  assert.match(source, /REAL · User outside zone/)
  assert.match(source, /fillColor: '#f97316'/)
  assert.match(source, /SIMULATED CITIZEN/)
})

test('Citizen remains disconnected from affected-population intelligence', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /affectedUserLocations|AFFECTED POPULATION|Real alert recipients/)
})
