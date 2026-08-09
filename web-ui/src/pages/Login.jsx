import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, MessageCircle, ShieldCheck, Smartphone } from 'lucide-react'
import { savePendingPhone, getStoredAuth } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'
import { startPhoneSignIn } from '../services/authService'

function sanitizePhone(value) {
  return String(value || '').replace(/\s+/g, '')
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { authenticated } = useAuth()
  const [phoneNumber, setPhoneNumber] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const sendInFlightRef = useRef(false)

  useEffect(() => {
    if (authenticated) {
      const from = location.state?.from || '/'
      navigate(from, { replace: true })
      return
    }

    const stored = getStoredAuth()
    if (stored.token) {
      navigate('/', { replace: true })
    }
  }, [authenticated, location.state, navigate])

  async function handleSubmit(event) {
    event.preventDefault()
    if (sendInFlightRef.current) return
    const normalized = sanitizePhone(phoneNumber)
    if (!/^\+[1-9]\d{7,14}$/.test(normalized)) {
      setError('Enter a valid phone number in E.164 format, for example +919876543210.')
      return
    }

    sendInFlightRef.current = true
    setLoading(true)
    setError('')
    try {
      console.debug('[Login] Attempting Firebase phone sign-in', { phoneNumber: normalized })
      await startPhoneSignIn(normalized)
      console.debug('[Login] Firebase phone sign-in started successfully')
      const maskedPhone = normalized
      const returnTo = location.state?.from || '/'
      savePendingPhone(normalized, maskedPhone, returnTo)
      navigate('/otp', { replace: true, state: { phoneNumber: normalized, maskedPhone, returnTo } })
    } catch (err) {
      setError(err?.message || 'Unable to send OTP right now.')
    } finally {
      setLoading(false)
      sendInFlightRef.current = false
    }
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
                Protect the dashboard with phone number OTP authentication.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
                LandSense now starts with a lightweight authentication gateway before the existing analytics, geofencing,
                and alert workflows load.
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
            <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Step 1 of 2</div>
            <h2 className="mt-2 text-2xl font-bold tracking-[-0.04em] text-white">Enter your phone number</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              We will send an OTP to your number and keep the existing dashboard untouched after login.
            </p>

            <form className="mt-8 space-y-4" onSubmit={handleSubmit}>
              <label className="block space-y-2">
                <span className="text-sm font-medium text-slate-200">Phone number</span>
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(event) => setPhoneNumber(event.target.value)}
                  placeholder="+919876543210"
                  autoComplete="tel"
                  className="w-full rounded-2xl border border-white/10 bg-[#060d17] px-4 py-3 text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300/50 focus:bg-[#09131f]"
                />
              </label>

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
                <span>Send OTP</span>
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
