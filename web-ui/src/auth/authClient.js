const API_BASE = window.location.origin

const STORAGE = {
  token: 'landsense_auth_token',
  refresh: 'landsense_auth_refresh_token',
  profile: 'landsense_auth_profile',
  pendingPhone: 'landsense_pending_phone',
  pendingMask: 'landsense_pending_phone_mask',
  pendingReturnTo: 'landsense_pending_return_to'
}

function safeJsonParse(value) {
  if (!value) return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

export function apiFetch(path, options = {}, token = '') {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  }).then(async (response) => {
    if (response.ok) return response.json()

    // Try automatic refresh on 401 using stored refresh token
    if (response.status === 401) {
      const stored = getStoredAuth()
      if (stored.refreshToken) {
        try {
          const r = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: stored.refreshToken })
          })
          if (r.ok) {
            const data = await r.json()
            // persist new tokens
            saveAuthSession({ access_token: data.access_token, refresh_token: data.refresh_token, profile: stored.profile })
            // retry original request with new token
            const retryHeaders = { ...headers, Authorization: `Bearer ${data.access_token}` }
            const retry = await fetch(`${API_BASE}${path}`, { ...options, headers: retryHeaders })
            if (retry.ok) return retry.json()
          }
        } catch (err) {
          // fallthrough to clear session
        }
      }

      // Refresh failed - clear local session and redirect to login
      clearAuthSession()
      try {
        window.location.replace('/login')
      } catch (e) {
        /* ignore */
      }
    }

    const text = await response.text()
    const error = new Error(text || 'Request failed')
    error.status = response.status
    throw error
  })
}

export function maskPhoneNumber(phoneNumber) {
  const value = String(phoneNumber || '').trim()
  if (value.length <= 7) return value
  return `${value.slice(0, 3)}${'*'.repeat(Math.max(4, value.length - 7))}${value.slice(-4)}`
}

export function getStoredAuth() {
  return {
    token: localStorage.getItem(STORAGE.token) || '',
    refreshToken: localStorage.getItem(STORAGE.refresh) || '',
    profile: safeJsonParse(localStorage.getItem(STORAGE.profile))
  }
}

export function saveAuthSession(session) {
  if (session?.access_token) localStorage.setItem(STORAGE.token, session.access_token)
  if (session?.refresh_token) localStorage.setItem(STORAGE.refresh, session.refresh_token)
  if (session?.profile) localStorage.setItem(STORAGE.profile, JSON.stringify(session.profile))
}

export function clearAuthSession() {
  localStorage.removeItem(STORAGE.token)
  localStorage.removeItem(STORAGE.refresh)
  localStorage.removeItem(STORAGE.profile)
}

export function savePendingPhone(phoneNumber, maskedPhone, returnTo = '/') {
  sessionStorage.setItem(STORAGE.pendingPhone, phoneNumber)
  sessionStorage.setItem(STORAGE.pendingMask, maskedPhone || maskPhoneNumber(phoneNumber))
  sessionStorage.setItem(STORAGE.pendingReturnTo, returnTo || '/')
}

export function getPendingPhone() {
  return {
    phoneNumber: sessionStorage.getItem(STORAGE.pendingPhone) || '',
    maskedPhone: sessionStorage.getItem(STORAGE.pendingMask) || '',
    returnTo: sessionStorage.getItem(STORAGE.pendingReturnTo) || '/'
  }
}

export function clearPendingPhone() {
  sessionStorage.removeItem(STORAGE.pendingPhone)
  sessionStorage.removeItem(STORAGE.pendingMask)
  sessionStorage.removeItem(STORAGE.pendingReturnTo)
}

export function sendOtp(phoneNumber) {
  return apiFetch('/send-otp', {
    method: 'POST',
    body: JSON.stringify({ phone_number: phoneNumber })
  })
}

export function verifyOtp(phoneNumber, otp) {
  return apiFetch('/verify-otp', {
    method: 'POST',
    body: JSON.stringify({ phone_number: phoneNumber, otp })
  })
}

export function fetchProfile(token) {
  return apiFetch('/profile', { method: 'GET' }, token)
}

export function logout(token) {
  return apiFetch('/logout', { method: 'POST' }, token)
}
