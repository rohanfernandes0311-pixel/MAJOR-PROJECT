import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, MapPin, MessageCircle, ShieldCheck, Shield, Smartphone } from 'lucide-react'
import { savePendingPhone, getStoredAuth } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { startPhoneSignIn } from '../services/authService'
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
      await startPhoneSignIn(normalized)
      const maskedPhone = `+91 ******${phoneNumber.slice(-4)}`
      const returnTo = loginIntent === 'admin' ? '/admin' : (location.state?.from || '/')
      savePendingPhone(normalized, maskedPhone, returnTo, loginIntent)
      navigate('/otp', { replace: true, state: { phoneNumber: normalized, maskedPhone, returnTo, loginIntent } })
    } catch (err) {
      setError(err?.message || 'Unable to send OTP right now.')
    } finally {
      setLoading(false)
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
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_30%),radial-gradient(circle_at_top_right,_rgba(16,185,129,0.14),_transparent_28%),linear-gradient(180deg,#040b14_0%,#07111d_48%,#081321_100%)] text-white">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid w-full gap-6 lg:grid-cols-[1.1fr_0.9fr] lg:gap-8">
          <motion.section
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl backdrop-blur-2xl sm:p-8"
          >
            <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(125,211,252,0.12),transparent_38%,rgba(16,185,129,0.08)_78%)]" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.26em] text-cyan-100">
                <ShieldCheck className="h-4 w-4" />
                Secure LandSense Access
              </div>
              <h1 className="mt-5 max-w-xl text-4xl font-black tracking-[-0.05em] text-white sm:text-5xl">
                Landslide intelligence and emergency awareness.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
                Choose your access area, then verify your phone with the existing secure OTP flow.
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                <FeatureCard icon={Smartphone} title="Mobile-first" copy="Optimized for quick access on phones and tablets." />
                <FeatureCard icon={MessageCircle} title="OTP delivery" copy="Send a 6-digit code through a replaceable SMS provider." />
                <FeatureCard icon={ShieldCheck} title="JWT gateway" copy="Issue a signed token only after verification succeeds." />
              </div>
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.08 }}
            className="rounded-[2rem] border border-white/10 bg-[#09131f]/90 p-6 shadow-2xl backdrop-blur-2xl sm:p-8"
          >
            <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Secure sign in</div>
            <h2 className="mt-2 text-2xl font-bold tracking-[-0.04em] text-white">Choose your access area</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">Your authenticated account role, not this choice, determines where you can go.</p>

            <div className="mt-6 space-y-3">
              <AccessChoice
                active={loginIntent === 'citizen'}
                icon={MapPin}
                title="Citizen Login"
                subtitle="Public safety monitoring"
                copy="Monitor your location, landslide risk and safety guidance."
                action="Continue as Citizen"
                onClick={() => setLoginIntent('citizen')}
              />
              <AccessChoice
                active={loginIntent === 'admin'}
                icon={Shield}
                title="Admin Login"
                subtitle="Emergency operations centre"
                copy="Monitor users, risk zones, events and alerts."
                action="Admin Login"
                onClick={() => setLoginIntent('admin')}
              />
            </div>

            <form className="mt-6 space-y-4 border-t border-white/10 pt-6" onSubmit={handleSubmit}>
              <div
                className="space-y-2"
                onFocus={() => setShowPhoneSuggestions(true)}
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget)) setShowPhoneSuggestions(false)
                }}
              >
                <label htmlFor="phone-number" className="block text-sm font-medium text-slate-200">Phone number</label>
                <div className="flex overflow-hidden rounded-2xl border border-white/10 bg-[#060d17] transition focus-within:border-cyan-300/50 focus-within:bg-[#09131f]">
                  <span className="flex items-center border-r border-white/10 bg-white/5 px-4 font-semibold text-slate-200" aria-label="India country code">+91</span>
                  <input
                    id="phone-number"
                    type="tel"
                    inputMode="numeric"
                    value={phoneNumber}
                    onChange={(event) => {
                      const next = event.target.value
                      if (!/^\d*$/.test(next) || next.length > 10) {
                        setError('Enter digits only, without the +91 country code.')
                        return
                      }
                      setPhoneNumber(next)
                      setError('')
                    }}
                    placeholder="9876543210"
                    maxLength="10"
                    pattern="[0-9]{10}"
                    autoComplete="tel-national"
                    aria-label="10-digit Indian mobile number"
                    className="min-w-0 flex-1 bg-transparent px-4 py-3 text-white outline-none placeholder:text-slate-500"
                  />
                </div>
                <span className="block text-xs text-slate-400">Enter the 10-digit mobile number only.</span>
                {showPhoneSuggestions && previousPhoneNumbers.length ? (
                  <div className="rounded-2xl border border-white/10 bg-[#060d17] p-2 shadow-xl" aria-label="Previously used phone numbers">
                    <div className="flex items-center justify-between gap-3 px-2 py-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Previously used</span>
                      <button type="button" onClick={clearSavedPhoneNumbers} className="text-xs font-semibold text-slate-400 hover:text-rose-200">Clear saved numbers</button>
                    </div>
                    <div className="mt-1 space-y-1">
                      {previousPhoneNumbers.map((phone) => (
                        <button
                          key={phone}
                          type="button"
                          onClick={() => selectPreviousPhoneNumber(phone)}
                          className="block w-full rounded-xl px-3 py-2 text-left text-sm font-semibold text-slate-100 transition hover:bg-white/10 focus:bg-white/10 focus:outline-none"
                        >
                          {maskPreviousPhoneNumber(phone)}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              {error ? (
                <div className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                  {error}
                </div>
              ) : null}

              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 to-emerald-400 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-950/20 border-t-slate-950" />
                ) : (
                  <ArrowRight className="h-4 w-4" />
                )}
                <span>{loading ? 'Sending OTP…' : 'Send OTP'}</span>
              </button>
            </form>

            <div className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm leading-6 text-slate-300">
              The dashboard, analytics, route planner, and geofencing flow stay unchanged after authentication.
            </div>
            <div id="recaptcha-container" className="sr-only" aria-hidden="true" />
          </motion.section>
        </div>
      </div>
    </div>
  )
}

function FeatureCard({ icon: Icon, title, copy }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-black/20 p-4 shadow-inner shadow-black/20">
      <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-white/10 text-cyan-200">
        <Icon className="h-5 w-5" />
      </div>
      <div className="mt-4 text-sm font-semibold text-white">{title}</div>
      <p className="mt-1 text-sm leading-6 text-slate-300">{copy}</p>
    </div>
  )
}

function AccessChoice({ active, icon: Icon, title, subtitle, copy, action, onClick }) {
  return (
    <section className={`rounded-2xl border p-4 transition ${active ? 'border-cyan-300/40 bg-cyan-400/10 shadow-lg shadow-cyan-950/30' : 'border-white/10 bg-black/20'}`}>
      <div className="flex gap-3">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${active ? 'bg-cyan-300 text-slate-950' : 'bg-white/10 text-cyan-200'}`}><Icon className="h-5 w-5" /></div>
        <div className="min-w-0"><h3 className="font-semibold text-white">{title}</h3><p className="mt-0.5 text-sm text-cyan-100">{subtitle}</p><p className="mt-2 text-sm leading-5 text-slate-300">{copy}</p></div>
      </div>
      <button type="button" onClick={onClick} className={`mt-4 w-full rounded-xl px-4 py-2.5 text-sm font-semibold transition ${active ? 'bg-cyan-300 text-slate-950 hover:bg-cyan-200' : 'border border-white/15 bg-white/5 text-white hover:bg-white/10'}`}>{action}</button>
    </section>
  )
}
