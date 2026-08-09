import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { clearAuthSession, fetchProfile, getStoredAuth, logout as apiLogout, saveAuthSession } from './authClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [token, setToken] = useState('')
  const [profile, setProfile] = useState(null)

  useEffect(() => {
    const stored = getStoredAuth()
    if (!stored.token) {
      setStatus('anonymous')
      return
    }

    let active = true
    ;(async () => {
      try {
        const response = await fetchProfile(stored.token)
        if (!active) return
        setToken(stored.token)
        setProfile(response?.profile || stored.profile || null)
        saveAuthSession({ access_token: stored.token, refresh_token: stored.refreshToken, profile: response?.profile || stored.profile || null })
        setStatus('authenticated')
        return
      } catch (err) {
        // Attempt refresh using stored refresh token
      }

      if (!stored.refreshToken) {
        if (!active) return
        clearAuthSession()
        setToken('')
        setProfile(null)
        setStatus('anonymous')
        return
      }

      try {
        const resp = await fetch('/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: stored.refreshToken })
        })
        if (!resp.ok) throw new Error('Refresh failed')
        const data = await resp.json()
        saveAuthSession({ access_token: data.access_token, refresh_token: data.refresh_token, profile: data.profile })
        const profileResp = await fetchProfile(data.access_token)
        if (!active) return
        setToken(data.access_token)
        setProfile(profileResp?.profile || null)
        setStatus('authenticated')
      } catch (err) {
        if (!active) return
        clearAuthSession()
        setToken('')
        setProfile(null)
        setStatus('anonymous')
      }
    })()

    return () => {
      active = false
    }
  }, [])

  const signIn = useCallback((session) => {
    saveAuthSession(session)
    setToken(session?.access_token || '')
    setProfile(session?.profile || null)
    setStatus('authenticated')
  }, [])

  const signOut = useCallback(async () => {
    const currentToken = token || getStoredAuth().token
    if (currentToken) {
      try {
        await apiLogout(currentToken)
      } catch {
        // Local sign-out should still succeed if the backend is unavailable.
      }
    }
    clearAuthSession()
    setToken('')
    setProfile(null)
    setStatus('anonymous')
  }, [token])

  const value = useMemo(
    () => ({
      status,
      ready: status !== 'loading',
      loading: status === 'loading',
      authenticated: status === 'authenticated',
      token,
      profile,
      signIn,
      signOut
    }),
    [status, token, profile, signIn, signOut]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
