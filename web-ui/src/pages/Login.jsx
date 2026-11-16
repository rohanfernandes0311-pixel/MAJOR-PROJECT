import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, MapPin, Shield } from 'lucide-react'
import { savePendingPhone, getStoredAuth } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { startPhoneSignIn } from '../services/authService'
import { createRecaptcha } from '../authentication/firebase'
import { discardRecaptchaVerifier, ensureRecaptchaVerifier, isStaleRecaptchaError } from '../authentication/recaptchaLifecycle'
import { getIndianNationalNumber, isValidIndianMobileNumber, toIndianE164 } from '../services/indianPhone'
import { clearPreviousPhoneNumbers, loadPreviousPhoneNumbers, maskPreviousPhoneNumber } from '../services/phoneHistory'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { authenticated, profile } = useAuth()
  const [phoneNumber, setPhoneNumber] = useState(() => getIndianNationalNumber(location.state?.editPhoneNumber))
  const [loginIntent, setLoginIntent] = useState(() => location.state?.loginIntent === 'admin' ? 'admin' : 'citizen')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [previousPhoneNumbers, setPreviousPhoneNumbers] = useState(loadPreviousPhoneNumbers)
  const [showPhoneSuggestions, setShowPhoneSuggestions] = useState(false)
  const sendInFlightRef = useRef(false)
  const recaptchaContainerRef = useRef(null)
  const recaptchaVerifierRef = useRef(null)
  const recaptchaInFlightRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (!recaptchaInFlightRef.current) {
        discardRecaptchaVerifier(recaptchaVerifierRef)
      }
    }
  }, [])

  useEffect(() => {
    if (authenticated) {
      navigate(String(profile?.role || '').toLowerCase() === 'admin' ? '/admin' : '/', { replace: true })
      return
    }

    const stored = getStoredAuth()
    if (stored.token) {
      navigate('/', { replace: true })
    }
  }, [authenticated, navigate, profile?.role])

  useEffect(() => {
    if (!location.state?.editPhoneNumber) return
    setPhoneNumber(getIndianNationalNumber(location.state.editPhoneNumber))
    setLoginIntent(location.state?.loginIntent === 'admin' ? 'admin' : 'citizen')
  }, [location.state])

  async function handleSubmit(event) {
    event.preventDefault()
    if (sendInFlightRef.current) return
    if (!isValidIndianMobileNumber(phoneNumber)) {
      setError('Enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9.')
      return
    }
    const normalized = toIndianE164(phoneNumber)

    sendInFlightRef.current = true
    setLoading(true)
    setError('')
    try {
      const verifier = ensureRecaptchaVerifier(
        recaptchaVerifierRef,
        recaptchaContainerRef.current,
        createRecaptcha,
      )
      recaptchaInFlightRef.current = true
      await startPhoneSignIn(normalized, verifier)
      const maskedPhone = `+91 ******${phoneNumber.slice(-4)}`
      const returnTo = loginIntent === 'admin' ? '/admin' : (location.state?.from || '/')
      savePendingPhone(normalized, maskedPhone, returnTo, loginIntent)
      navigate('/otp', { replace: true, state: { phoneNumber: normalized, maskedPhone, returnTo, loginIntent } })
    } catch (err) {
      if (isStaleRecaptchaError(err)) {
        discardRecaptchaVerifier(recaptchaVerifierRef)
      }
      setError(err?.message || 'Unable to send OTP right now.')
    } finally {
      recaptchaInFlightRef.current = false
      if (!mountedRef.current) {
        discardRecaptchaVerifier(recaptchaVerifierRef)
      }
      if (mountedRef.current) setLoading(false)
      sendInFlightRef.current = false
    }
  }

  function selectPreviousPhoneNumber(phone) {
    setPhoneNumber(getIndianNationalNumber(phone))
    setError('')
    setShowPhoneSuggestions(false)
  }

  function clearSavedPhoneNumbers() {
    if (!window.confirm('Clear previously used phone numbers from this browser?')) return
    clearPreviousPhoneNumbers()
    setPreviousPhoneNumbers([])
    setShowPhoneSuggestions(false)
  }

  return (
    <div className="auth-shell login-shell">
      <div className="mx-auto grid min-h-screen max-w-6xl items-center gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(360px,448px)] lg:gap-8 lg:py-10">
          <section aria-label="LandSense branding" className="w-full">
            <img
              src="/images/landsense-wordmark-hero.jpg"
              alt="LandSense — Detect, Predict, Protect"
              width="1600"
              height="900"
              sizes="(min-width: 1024px) 62vw, 100vw"
              fetchPriority="high"
              decoding="async"
              className="block aspect-video h-auto w-full rounded-xl object-contain"
            />
          </section>
          <motion.section
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="ls-card w-full p-6 sm:p-8"
          >
            <div className="flex items-center gap-3">
              <img src="/icons/landsense-logo.png" alt="" className="h-10 w-10 shrink-0 rounded-xl object-contain" />
              <div><h1 className="text-xl font-bold tracking-tight text-[#18211b]">LandSense</h1><p className="text-sm text-[#647067]">Location-aware landslide risk and safety</p></div>
            </div>
            <h2 className="mt-8 text-lg font-semibold text-[#18211b]">Sign in</h2>
            <p className="mt-1 text-sm text-[#647067]">Choose your dashboard and verify your mobile number.</p>

            <div className="mt-5 grid grid-cols-2 gap-2">
              <AccessChoice
                active={loginIntent === 'citizen'}
                icon={MapPin}
                title="Citizen Login"
                onClick={() => setLoginIntent('citizen')}
              />
              <AccessChoice
                active={loginIntent === 'admin'}
                icon={Shield}
                title="Admin Login"
                onClick={() => setLoginIntent('admin')}
              />
            </div>

            <form className="mt-6 space-y-4 border-t border-[#dfe5df] pt-6" onSubmit={handleSubmit}>
              <div
                className="space-y-2"
                onFocus={() => setShowPhoneSuggestions(true)}
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget)) setShowPhoneSuggestions(false)
                }}
              >
                <label htmlFor="phone-number" className="block text-sm font-medium text-[#26352b]">Mobile number</label>
                <div className="flex overflow-hidden rounded-xl border border-[#cfd8d1] bg-white transition focus-within:border-[#1f5d42] focus-within:ring-2 focus-within:ring-[#1f5d42]/10">
                  <span className="flex items-center border-r border-[#dfe5df] bg-[#f4f6f3] px-4 font-semibold text-[#455349]" aria-label="India country code">+91</span>
                  <input
                    id="phone-number"
                    type="tel"
                    inputMode="numeric"
                    value={phoneNumber}
                    onChange={(event) => {
                      const next = event.target.value.trim().replace(/\s/g, '').replace(/^\+91/, '')
                      if (!/^\d*$/.test(next)) {
                        setError('Enter digits only, optionally with the +91 country code.')
                        return
                      }
                      setPhoneNumber(next)
                      setError(next.length > 10 ? 'Enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9.' : '')
                    }}
                    placeholder="9876543210"
                    pattern="[0-9]{10}"
                    autoComplete="tel-national"
                    aria-label="10-digit Indian mobile number"
                    className="min-w-0 flex-1 bg-transparent px-4 py-3 text-[#18211b] outline-none placeholder:text-slate-400"
                  />
                </div>
                <span className="block text-xs text-[#647067]">10-digit Indian mobile number</span>
                {showPhoneSuggestions && previousPhoneNumbers.length ? (
                  <div className="rounded-xl border border-[#dfe5df] bg-white p-2 shadow-lg" aria-label="Previously used phone numbers">
                    <div className="flex items-center justify-between gap-3 px-2 py-1">
                      <span className="text-xs font-semibold text-[#647067]">Previously used</span>
                      <button type="button" onClick={clearSavedPhoneNumbers} className="text-xs font-semibold text-[#647067] hover:text-red-700">Clear</button>
                    </div>
                    <div className="mt-1 space-y-1">
                      {previousPhoneNumbers.map((phone) => (
                        <button
                          key={phone}
                          type="button"
                          onClick={() => selectPreviousPhoneNumber(phone)}
                          className="block w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-[#26352b] transition hover:bg-[#f4f6f3] focus:bg-[#f4f6f3] focus:outline-none"
                        >
                          {maskPreviousPhoneNumber(phone)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                  {error}
                </div>
              ) : null}

              <button
                type="submit"
                disabled={loading}
                className="ls-primary-action inline-flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                ) : (
                  <ArrowRight className="h-4 w-4" />
                )}
                <span>{loading ? 'Sending OTP…' : 'Send OTP'}</span>
              </button>
            </form>

            <p className="mt-5 text-center text-xs text-[#647067]">Your account role controls dashboard access.</p>
            <div ref={recaptchaContainerRef} className="sr-only" aria-hidden="true" />
          </motion.section>
      </div>
      <section
        aria-labelledby="about-landsense-title"
        className="mx-auto w-full max-w-6xl border-t border-[#d8e0dd] px-4 py-5 text-center sm:px-6"
      >
        <h2 id="about-landsense-title" className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[#2f5d50]">
          ABOUT LANDSense
        </h2>
        <p className="mt-2 text-[13px] font-normal text-[#18211b]">Developed by</p>
        <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[14px] font-medium text-[#647067]">
          <span>Rohan Fernandes</span>
          <span>Prajwal M</span>
          <span>Vikas M Gowda</span>
          <span>Pavithra R</span>
        </div>
      </section>
    </div>
  )
}

function AccessChoice({ active, icon: Icon, title, onClick }) {
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={`flex items-center gap-2 rounded-xl border px-3 py-3 text-left text-sm font-semibold transition ${active ? 'border-[#1f5d42] bg-[#eef5f0] text-[#174832] ring-1 ring-[#1f5d42]/10' : 'border-[#dfe5df] bg-white text-[#536158] hover:bg-[#f8faf8]'}`}>
      <Icon className="h-4 w-4" />{title}
    </button>
  )
}
