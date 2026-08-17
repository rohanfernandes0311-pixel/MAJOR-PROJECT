const INDIA_DIAL_CODE = '+91'

function isValidIndianMobileNumber(value) {
  return /^[6-9]\d{9}$/.test(String(value || ''))
}

function toIndianE164(value) {
  const nationalNumber = String(value || '')
  if (!isValidIndianMobileNumber(nationalNumber)) {
    throw new Error('Enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9.')
  }
  return `${INDIA_DIAL_CODE}${nationalNumber}`
}

function getIndianNationalNumber(value) {
  const phone = String(value || '').trim()
  if (/^\+91\d{10}$/.test(phone)) return phone.slice(3)
  if (/^91\d{10}$/.test(phone)) return phone.slice(2)
  return /^\d{0,10}$/.test(phone) ? phone : ''
}

export { INDIA_DIAL_CODE, getIndianNationalNumber, isValidIndianMobileNumber, toIndianE164 }
