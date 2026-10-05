import test from 'node:test'
import assert from 'node:assert/strict'
import { scenarioKey, toggleRecipient, toggleDemoAdmin, exportSelections, activeAdminActor, simulationExcelFilename } from './simulationRecipients.js'
import { initialDemoReview } from './simulationDemo.js'

const people = [
  { displayId: 'one', inside: true, recipientEligible: true },
  { displayId: 'four', inside: true, recipientEligible: true },
  { displayId: 'two', inside: false, recipientEligible: false },
]

test('single simulation download uses the selected location and risk filename', () => {
  assert.equal(simulationExcelFilename([{ location: 'Chittalli', risk: 'HIGH' }]), 'LANDsense_SIMULATION_Chittalli_HIGH_httpSMS.xlsx')
  assert.equal(simulationExcelFilename([{ location: 'Virajpet', risk: 'CRITICAL' }]), 'LANDsense_SIMULATION_Virajpet_CRITICAL_httpSMS.xlsx')
})

test('multiple simulation groups use the combined workbook filename', () => {
  assert.equal(simulationExcelFilename([{ location: 'Madikeri', risk: 'HIGH' }, { location: 'Virajpet', risk: 'CRITICAL' }]), 'LANDsense_SIMULATION_httpSMS.xlsx')
})

test('Demo Admin selection is explicit and independent of geofencing', () => {
  const admins = [{ recipientId: 'admin-two', selectable: true }, { recipientId: 'admin-three', selectable: true }, { recipientId: 'invalid', selectable: false }]
  assert.deepEqual(toggleDemoAdmin([], 'admin-two', true, admins), ['admin-two'])
  assert.deepEqual(toggleDemoAdmin(['admin-two'], 'admin-two', true, admins), ['admin-two'])
  assert.deepEqual(toggleDemoAdmin(['admin-two'], 'admin-two', false, admins), [])
  assert.deepEqual(toggleDemoAdmin([], 'invalid', true, admins), [])
  assert.deepEqual(toggleDemoAdmin([], 'unknown', true, admins), [])
})

test('Demo Admin only and mixed exports preserve separate location/risk drafts', () => {
  const drafts = {
    [scenarioKey('Madikeri', 'HIGH')]: { scenario: { location: 'Madikeri', risk: 'HIGH', revision: 'm' }, selected: [], demoAdmins: ['admin-two'], message: 'Madikeri HIGH' },
    [scenarioKey('Virajpet', 'CRITICAL')]: { scenario: { location: 'Virajpet', risk: 'CRITICAL', revision: 'v' }, selected: ['one'], demoAdmins: ['admin-three'], message: 'Virajpet CRITICAL' },
    [scenarioKey('Madikeri', 'CRITICAL')]: { scenario: { location: 'Madikeri', risk: 'CRITICAL', revision: 'c' }, selected: [], demoAdmins: [], message: 'Madikeri CRITICAL' },
  }
  const selections = exportSelections(drafts)
  assert.equal(selections.length, 2)
  assert.deepEqual(selections[0], { location: 'Madikeri', risk: 'HIGH', revision: 'm', message: 'Madikeri HIGH', recipient_ids: [], demo_admin_recipient_ids: ['admin-two'] })
  assert.deepEqual(selections[1], { location: 'Virajpet', risk: 'CRITICAL', revision: 'v', message: 'Virajpet CRITICAL', recipient_ids: ['one'], demo_admin_recipient_ids: ['admin-three'] })
  assert.deepEqual(exportSelections({}), []) // The existing reset clears all draft selections.
})
test('case 9: checking one eligible user never selects another', () => {
  assert.deepEqual(toggleRecipient([], 'one', true, people), ['one'])
  assert.deepEqual(toggleRecipient(['one'], 'one', true, people), ['one'])
  assert.deepEqual(toggleRecipient(['one'], 'one', false, people), [])
  assert.deepEqual(toggleRecipient([], 'two', true, people), [])
})
test('case 10: location and risk selections remain independent', () => {
  const drafts = {
    [scenarioKey('Virajpet', 'HIGH')]: { scenario: { location: 'Virajpet', risk: 'HIGH', revision: 'v' }, selected: ['one'], message: 'HIGH' },
    [scenarioKey('Madikeri', 'CRITICAL')]: { scenario: { location: 'Madikeri', risk: 'CRITICAL', revision: 'm' }, selected: ['two'], message: 'CRITICAL' },
    [scenarioKey('Chittalli', 'HIGH')]: { scenario: { location: 'Chittalli', risk: 'HIGH', revision: 'c' }, selected: [], message: 'HIGH' },
  }
  const selections = exportSelections(drafts)
  assert.deepEqual(selections.map(s => [s.location, s.risk, s.recipient_ids, s.message]), [
    ['Virajpet', 'HIGH', ['one'], 'HIGH'], ['Madikeri', 'CRITICAL', ['two'], 'CRITICAL'],
  ])
  assert.deepEqual(exportSelections({}), [])
  assert.notEqual(scenarioKey('Virajpet', 'HIGH'), scenarioKey('Virajpet', 'CRITICAL'))
})
test('opening a simulation review never preselects eligible users', () => {
  const review = initialDemoReview({ active: true, state: { enabled: true, is_simulation: true, alert_preview: { message: 'HIGH' } }, preview: { recipients: [{ display_id: 'one', sms_eligible: true }] } })
  assert.deepEqual(review.selected, [])
})

test('actor follows active scenario and disappears on reset or location change', () => {
  const actor = { status: 'available', is_simulation: true, recipientEligible: false }
  const scenario = { location: 'Madikeri', risk: 'HIGH', adminActor: actor }
  assert.equal(activeAdminActor(scenario, 'Madikeri', 'HIGH', true), actor)
  assert.equal(activeAdminActor(scenario, 'Virajpet', 'HIGH', true), null)
  assert.equal(activeAdminActor(scenario, 'Madikeri', 'CRITICAL', true), null)
  assert.equal(activeAdminActor(scenario, 'Madikeri', 'HIGH', false), null)
  assert.equal(activeAdminActor(null, 'Madikeri', 'HIGH', false), null)
  assert.deepEqual(exportSelections({}), [])
})

test('actor overlay is gated by simulation mode and absent from Public dashboard', async () => {
  const { readFile } = await import('node:fs/promises')
  const map = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  const page = await readFile(new URL('../pages/SimulationDemo.jsx', import.meta.url), 'utf8')
  const publicPage = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(map, /adminSimulationActor = null/)
  assert.match(map, /showSimulationLayers && adminSimulationActor\?\.status === 'available' && adminSimulationActor\?\.is_simulation === true/)
  assert.match(map, /ADMIN SIMULATION ACTOR/)
  assert.match(page, /adminSimulationActor=\{activeAdminActor\(scenario, location, risk, current\)\}/)
  assert.match(page, /<MapView key="simulation-inactive" zones=\{EMPTY\} \/>/)
  assert.doesNotMatch(publicPage, /adminSimulationActor|adminActor/)
  assert.doesNotMatch(page, /location-update|watchPosition|getCurrentPosition/)
})
