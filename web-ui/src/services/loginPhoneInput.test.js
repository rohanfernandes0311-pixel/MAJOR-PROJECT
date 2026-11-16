import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { runInNewContext } from 'node:vm'
import { isValidIndianMobileNumber, toIndianE164 } from './indianPhone.js'

// Source parsing must work with both Windows CRLF and Unix LF checkouts.
const source = (await readFile(new URL('../pages/Login.jsx', import.meta.url), 'utf8')).replace(/\r\n/g, '\n')
const input = source.match(/<input\s+id="phone-number"[\s\S]*?\/>/)[0]
const changeBody = input.match(/onChange=\{\(event\) => \{([\s\S]*?)\n\s*\}\}/)[1]
const submitBody = source.match(/async function handleSubmit\(event\) \{([\s\S]*?)\n  \}\n/)[1]

function createLogin() {
  const calls = []
  const verifier = {}
  const context = {
    phoneNumber: '',
    error: '',
    isValidIndianMobileNumber,
    toIndianE164,
    setPhoneNumber: (value) => { context.phoneNumber = value },
    setError: (value) => { context.error = value },
    setLoading: () => {},
    sendInFlightRef: { current: false },
    recaptchaInFlightRef: { current: false },
    recaptchaVerifierRef: { current: verifier },
    recaptchaContainerRef: { current: {} },
    mountedRef: { current: true },
    ensureRecaptchaVerifier: () => verifier,
    createRecaptcha: () => verifier,
    startPhoneSignIn: async (...args) => { calls.push(args) },
    savePendingPhone: (...args) => { context.pendingPhone = args },
    navigate: (...args) => { context.navigation = args },
    loginIntent: 'citizen',
    location: { state: {} },
  }
  const change = runInNewContext(`(event) => {${changeBody}}`, context)
  const submit = runInNewContext(`async (event) => {${submitBody}}`, context)
  return {
    context,
    calls,
    verifier,
    change: (value) => change({ target: { value } }),
    submit: () => submit({ preventDefault() {} }),
  }
}

test('phone input allows native paste and preserves the visible country prefix', () => {
  assert.doesNotMatch(input, /maxLength|onPaste|onKeyDown|onKeyPress/)
  assert.match(source, /aria-label="India country code">\+91<\/span>/)
})

test('normal typing accepts each partial value through all ten digits', () => {
  const login = createLogin()
  for (let length = 1; length <= 10; length += 1) {
    const value = '9876543210'.slice(0, length)
    login.change(value)
    assert.equal(login.context.phoneNumber, value)
    assert.equal(login.context.error, '')
  }
})

for (const value of ['9876543210', '+919876543210', '+91 98765 43210', '98765 43210', ' \t+91 98765 43210\n ']) {
  test(`input normalizes ${JSON.stringify(value)} and sends OTP through the existing flow`, async () => {
    const login = createLogin()
    login.change(value)
    assert.equal(login.context.phoneNumber, '9876543210')
    assert.equal(login.context.error, '')
    await login.submit()
    assert.deepEqual(login.calls, [['+919876543210', login.verifier]])
    assert.equal(login.context.pendingPhone[0], '+919876543210')
    assert.equal(login.context.navigation[0], '/otp')
  })
}

test('invalid letters and symbols are rejected by the change handler', () => {
  for (const value of ['letters', '98765abc10', '98765-43210', '9876543210!', '+449876543210', '++919876543210']) {
    const login = createLogin()
    login.change(value)
    assert.equal(login.context.phoneNumber, '')
    assert.ok(login.context.error)
  }
})

for (const value of ['987654321', '98765432101', '987654321012', '+9198765432101']) {
  test(`invalid length ${JSON.stringify(value)} reports an error without sending OTP`, async () => {
    const login = createLogin()
    login.change(value)
    await login.submit()
    assert.match(login.context.error, /10-digit/)
    assert.equal(login.calls.length, 0)
  })
}
