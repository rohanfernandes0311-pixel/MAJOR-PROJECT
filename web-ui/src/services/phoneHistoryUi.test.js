import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('Login shows masked local suggestions while keeping +91 fixed', async () => {
  const source = await readFile(new URL('../pages/Login.jsx', import.meta.url), 'utf8')
  assert.match(source, /loadPreviousPhoneNumbers/)
  assert.match(source, /maskPreviousPhoneNumber\(phone\)/)
  assert.match(source, /aria-label="India country code">\+91/)
  assert.match(source, /getIndianNationalNumber\(phone\)/)
  assert.match(source, /'Send OTP'/)
})

test('selecting history only populates the field and never starts OTP', async () => {
  const source = await readFile(new URL('../pages/Login.jsx', import.meta.url), 'utf8')
  const selectionBody = source.match(/function selectPreviousPhoneNumber\(phone\) \{([\s\S]*?)\n  \}/)?.[1] || ''
  assert.match(selectionBody, /setPhoneNumber/)
  assert.doesNotMatch(selectionBody, /startPhoneSignIn|navigate|savePendingPhone/)
})

test('phone history is recorded only after successful Firebase OTP exchange', async () => {
  const source = await readFile(new URL('../pages/OTP.jsx', import.meta.url), 'utf8')
  const confirmIndex = source.indexOf('await confirmOtpAndExchange(code)')
  const rememberIndex = source.indexOf('rememberPreviousPhoneNumber(phoneNumber)')
  assert.ok(confirmIndex >= 0)
  assert.ok(rememberIndex > confirmIndex)
  assert.equal((source.match(/rememberPreviousPhoneNumber\(/g) || []).length, 1)
})

test('clearing history uses confirmation and does not call authentication clearing', async () => {
  const source = await readFile(new URL('../pages/Login.jsx', import.meta.url), 'utf8')
  const clearBody = source.match(/function clearSavedPhoneNumbers\(\) \{([\s\S]*?)\n  \}/)?.[1] || ''
  assert.match(clearBody, /window\.confirm/)
  assert.match(clearBody, /clearPreviousPhoneNumbers/)
  assert.doesNotMatch(clearBody, /clearAuthSession|signOut|Firebase/)
})
