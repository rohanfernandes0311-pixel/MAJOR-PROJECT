import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AlertNotificationManager,
  alertNotificationStorageKey,
  buildNotificationContent
} from './alertNotificationManager.js'

function memoryStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key)
  }
}

const alert = (id, overrides = {}) => ({
  id,
  risk_level: 'HIGH',
  message: `Alert ${id}`,
  timestamp: `2026-08-15T10:00:0${id}Z`,
  delivery_status: 'in_app_pending',
  ...overrides
})

test('permission denied/default mode establishes a baseline without displaying notifications', async () => {
  const shown = []
  const storage = memoryStorage()
  const manager = new AlertNotificationManager({ storage, showNotification: (...args) => shown.push(args) })

  assert.equal(await manager.observe([alert(1)], { notify: false }), 1)
  assert.equal(shown.length, 0)
  assert.deepEqual(JSON.parse(storage.getItem(alertNotificationStorageKey)), ['1'])
})

test('no alerts displays no notifications', async () => {
  const shown = []
  const manager = new AlertNotificationManager({ storage: memoryStorage(), showNotification: (...args) => shown.push(args) })

  assert.equal(await manager.observe([], { notify: true }), 0)
  assert.equal(shown.length, 0)
})

test('one new alert displays once and remains deduplicated after reload', async () => {
  const shown = []
  const storage = memoryStorage()
  const showNotification = (...args) => shown.push(args)
  const firstManager = new AlertNotificationManager({ storage, showNotification })

  await firstManager.observe([alert(1)], { notify: true })
  await firstManager.observe([alert(1)], { notify: true })
  const reloadedManager = new AlertNotificationManager({ storage, showNotification })
  await reloadedManager.observe([alert(1)], { notify: true })

  assert.equal(shown.length, 1)
  assert.equal(shown[0][0], 'LANDSense — HIGH')
  assert.equal(shown[0][1].body, 'Alert 1')
  assert.deepEqual(shown[0][1].data, { url: '/#targeted-alerts' })
})

test('multiple new alerts each display once', async () => {
  const shown = []
  const manager = new AlertNotificationManager({ storage: memoryStorage(), showNotification: (...args) => shown.push(args) })

  await manager.observe([alert(3), alert(2), alert(1)], { notify: true })
  await manager.observe([alert(3), alert(2), alert(1)], { notify: true })

  assert.equal(shown.length, 3)
})

test('simulation alert is clearly labeled and does not expose internal identifiers in notification data', () => {
  const content = buildNotificationContent(alert(7, {
    risk_level: 'CRITICAL',
    source_type: 'ADMIN_SIMULATION',
    message: 'Drill message'
  }))

  assert.equal(content.title, 'LANDSENSE DEMO ALERT')
  assert.equal(content.body, 'Drill message')
  assert.deepEqual(content.data, { url: '/#targeted-alerts' })
  assert.equal(content.actions[0].title, 'Open Dashboard')
})

test('failed browser display is retried rather than recorded as delivered', async () => {
  let attempts = 0
  const manager = new AlertNotificationManager({
    storage: memoryStorage(),
    showNotification: async () => {
      attempts += 1
      if (attempts === 1) throw new Error('suppressed')
    }
  })

  await manager.observe([alert(1)], { notify: true })
  await manager.observe([alert(1)], { notify: true })

  assert.equal(attempts, 2)
  assert.equal(manager.hasBeenObserved(alert(1)), true)
})
