import test from 'node:test'
import assert from 'node:assert/strict'
import { citizenLiveAlerts, AlertNotificationManager, buildNotificationContent } from './alertNotificationManager.js'

test('Citizen inbox excludes existing simulation tags while preserving real alert records', () => {
  const real = { id: 1, risk_level: 'HIGH', message: 'Live targeted alert', source_type: null }
  const drill = { id: 2, risk_level: 'CRITICAL', source_type: 'ADMIN_SIMULATION' }
  const alerts = [real, drill, { id: 3, simulation: true }, { id: 4, message: 'SIMULATED ALERT drill' }]
  assert.deepEqual(citizenLiveAlerts(alerts), [real])
  assert.equal(alerts.length, 4)
  assert.deepEqual(citizenLiveAlerts(undefined), [])
  assert.equal(buildNotificationContent(drill).title, 'LANDSENSE DEMO ALERT')
})

test('Citizen filtered notifications still deliver live alerts once across polls and reloads', async () => {
  const values = new Map()
  const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) }
  const shown = []
  const options = { storage, showNotification: (title, content) => shown.push(content.tag) }
  const alerts = [{ id: 1, risk_level: 'HIGH' }, { id: 2, risk_level: 'CRITICAL', source_type: 'ADMIN_SIMULATION' }]
  const manager = new AlertNotificationManager(options)
  await manager.observe(citizenLiveAlerts(alerts), { notify: true })
  await manager.observe(citizenLiveAlerts(alerts), { notify: true })
  await new AlertNotificationManager(options).observe(citizenLiveAlerts(alerts), { notify: true })
  assert.deepEqual(shown, ['landsense-targeted-1'])
})
