import { getIndianNationalNumber, isValidIndianMobileNumber, toIndianE164 } from './indianPhone.js'

const PHONE_HISTORY_KEY = 'landSense.previousPhoneNumbers'
const MAX_PHONE_HISTORY = 5

function normalizeHistoryPhone(value) {
  const nationalNumber = getIndianNationalNumber(value)
  return isValidIndianMobileNumber(nationalNumber) ? toIndianE164(nationalNumber) : ''
}

function getStorage(storage) {
  return storage || globalThis.localStorage
}

function loadPreviousPhoneNumbers(storage) {
  try {
    const parsed = JSON.parse(getStorage(storage).getItem(PHONE_HISTORY_KEY) || '[]')
    if (!Array.isArray(parsed)) return []
    return [...new Set(parsed.map(normalizeHistoryPhone).filter(Boolean))].slice(0, MAX_PHONE_HISTORY)
  } catch {
    return []
  }
}

function rememberPreviousPhoneNumber(phoneNumber, storage) {
  const normalized = normalizeHistoryPhone(phoneNumber)
  if (!normalized) return loadPreviousPhoneNumbers(storage)
  const history = loadPreviousPhoneNumbers(storage).filter((item) => item !== normalized)
  const next = [normalized, ...history].slice(0, MAX_PHONE_HISTORY)
  try {
    getStorage(storage).setItem(PHONE_HISTORY_KEY, JSON.stringify(next))
  } catch {
    // Login still succeeds if private browsing or browser policy blocks storage.
  }
  return next
}

function clearPreviousPhoneNumbers(storage) {
  try {
    getStorage(storage).removeItem(PHONE_HISTORY_KEY)
  } catch {
    // Clearing convenience history must not affect authentication.
  }
}

function maskPreviousPhoneNumber(phoneNumber) {
  const normalized = normalizeHistoryPhone(phoneNumber)
  return normalized ? `+91 ••••••${normalized.slice(-4)}` : ''
}

export {
  MAX_PHONE_HISTORY,
  PHONE_HISTORY_KEY,
  clearPreviousPhoneNumbers,
  loadPreviousPhoneNumbers,
  maskPreviousPhoneNumber,
  rememberPreviousPhoneNumber
}
