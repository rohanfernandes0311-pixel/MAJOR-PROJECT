import test from 'node:test'
import assert from 'node:assert/strict'
import {
  MAX_PHONE_HISTORY,
  PHONE_HISTORY_KEY,
  clearPreviousPhoneNumbers,
  loadPreviousPhoneNumbers,
  maskPreviousPhoneNumber,
  rememberPreviousPhoneNumber
} from './phoneHistory.js'

function memoryStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
    has: (key) => values.has(key)
  }
}

test('first-time browser has no phone suggestions', () => {
  assert.deepEqual(loadPreviousPhoneNumbers(memoryStorage()), [])
})

test('successful numbers are normalized, deduplicated, and moved to most-recent position', () => {
  const storage = memoryStorage()
  rememberPreviousPhoneNumber('+919876543210', storage)
  rememberPreviousPhoneNumber('+918765432109', storage)
  rememberPreviousPhoneNumber('+919876543210', storage)
  assert.deepEqual(loadPreviousPhoneNumbers(storage), ['+919876543210', '+918765432109'])
})

test('history is bounded and invalid values are ignored', () => {
  const storage = memoryStorage()
  for (const number of ['9876543210', '8765432109', '7654321098', '6543210987', '9987654321', '8876543210']) {
    rememberPreviousPhoneNumber(`+91${number}`, storage)
  }
  rememberPreviousPhoneNumber('not-a-phone', storage)
  assert.equal(loadPreviousPhoneNumbers(storage).length, MAX_PHONE_HISTORY)
  assert.equal(loadPreviousPhoneNumbers(storage)[0], '+918876543210')
})

test('suggestions expose only country code and last four digits', () => {
  const masked = maskPreviousPhoneNumber('+919876541833')
  assert.equal(masked, '+91 ••••••1833')
  assert.doesNotMatch(masked, /987654/)
})

test('clearing removes only the phone-history key', () => {
  const storage = memoryStorage()
  storage.setItem('landsense_auth_token', 'keep-me')
  rememberPreviousPhoneNumber('+919876543210', storage)
  clearPreviousPhoneNumbers(storage)
  assert.equal(storage.has(PHONE_HISTORY_KEY), false)
  assert.equal(storage.getItem('landsense_auth_token'), 'keep-me')
})
