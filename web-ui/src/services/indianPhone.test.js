import test from 'node:test'
import assert from 'node:assert/strict'
import { getIndianNationalNumber, isValidIndianMobileNumber, toIndianE164 } from './indianPhone.js'

test('accepts a valid 10-digit Indian mobile number and constructs E.164 once', () => {
  assert.equal(isValidIndianMobileNumber('9876543210'), true)
  assert.equal(toIndianE164('9876543210'), '+919876543210')
})

test('rejects short, alphabetic, duplicate-prefix, and invalid-leading-digit input', () => {
  for (const value of ['98765', '98765abc10', '+919876543210', '919876543210', '5876543210']) {
    assert.equal(isValidIndianMobileNumber(value), false)
    assert.throws(() => toIndianE164(value))
  }
})

test('recovers only the national number when editing an existing E.164 number', () => {
  assert.equal(getIndianNationalNumber('+919876543210'), '9876543210')
  assert.equal(getIndianNationalNumber('919876543210'), '9876543210')
  assert.equal(getIndianNationalNumber('9876543210'), '9876543210')
})
