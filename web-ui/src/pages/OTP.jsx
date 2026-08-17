import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, CheckCircle2, RefreshCw, ShieldAlert, Smartphone, Sparkles } from 'lucide-react'
import OTPInput from '../components/OTPInput'
import Countdown from '../components/Countdown'
import VerifyButton from '../components/VerifyButton'
import {
  clearPendingPhone,
  getPendingPhone,
  maskPhoneNumber,
  savePendingPhone,
} from '../auth/authClient'
import { confirmOtpAndExchange, isFirebaseSignInPending, resetPhoneSignIn, startPhoneSignIn } from '../services/authService'
import { useAuth } from '../auth/AuthProvider'
import { useLocation, useNavigate } from 'react-router-dom'
import { rememberPreviousPhoneNumber } from '../services/phoneHistory'

export default function OTP() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn, authenticated, profile } = useAuth()
  const [phoneNumber, setPhoneNumber] = useState('')
  const [maskedPhone, setMaskedPhone] = useState('')
  const [returnTo, setReturnTo] = useState('/')
  const [otp, setOtp] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [resending, setResending] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [cooldown, setCooldown] = useState(30)
  const [toast, setToast] = useState(null)
  const [accessDecision, setAccessDecision] = useState('')
  const verifyInFlightRef = useRef(false)
  const resendInFlightRef = useRef(false)

  const pending = useMemo(() => {
    const statePhone = location.state?.phoneNumber || ''
    const stateMask = location.state?.maskedPhone || ''
    const stored = getPendingPhone()
    return {
      phoneNumber: statePhone || stored.phoneNumber,
      maskedPhone: stateMask || stored.maskedPhone,
      returnTo: location.state?.returnTo || stored.returnTo || '/',
      loginIntent: location.state?.loginIntent || stored.loginIntent || 'citizen'
    }
  }, [location.state])

  useEffect(() => {
    if (authenticated && !accessDecision) {
      navigate(String(profile?.role || '').toLowerCase() === 'admin' ? '/admin' : '/', { replace: true })
    }
  }, [accessDecision, authenticated, navigate, profile?.role])

  useEffect(() => {
    if (!pending.phoneNumber) {
      navigate('/login', { replace: true })
      return
    }
    setPhoneNumber(pending.phoneNumber)
    setMaskedPhone(pending.maskedPhone || maskPhoneNumber(pending.phoneNumber))
    setReturnTo(pending.returnTo)
    setCooldown(30)
    const timer = window.setInterval(() => {
      setCooldown((current) => Math.max(0, current - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [navigate, pending.phoneNumber, pending.maskedPhone, pending.returnTo])

  async function handleVerify(code = otp) {
    if (verifyInFlightRef.current) return
    if (code.length !== 6) {
      setError('Enter the 6-digit OTP before verifying.')
      return
    }
    if (!isFirebaseSignInPending()) {
      setError('OTP session expired. Please resend OTP.')
      return
    }
    verifyInFlightRef.current = true
    setVerifying(true)
    setError('')
    setSuccess('')
    try {
      const data = await confirmOtpAndExchange(code)
      const verifiedRole = String(data?.profile?.role || '').toLowerCase()
      const adminRequested = pending.loginIntent === 'admin'
      const isAdmin = verifiedRole === 'admin'
      if (adminRequested && !isAdmin) {
        setAccessDecision('citizen-admin-blocked')
      }
      rememberPreviousPhoneNumber(phoneNumber)
      signIn(data)
      clearPendingPhone()
      setSuccess(adminRequested && !isAdmin ? 'Verification successful.' : 'Verification successful. Redirecting to the dashboard...')
      setToast({ tone: 'success', message: 'Phone number verified successfully.' })
      if (!adminRequested || isAdmin) {
        navigate(isAdmin ? '/admin' : '/', { replace: true })
      }
    } catch (err) {
      setError(err?.message || 'Verification failed.')
      setToast({ tone: 'error', message: err?.message || 'Verification failed.' })
    } finally {
      setVerifying(false)
      verifyInFlightRef.current = false
    }
  }

  async function handleResend() {
    if (cooldown > 0 || resending || resendInFlightRef.current) return
    resendInFlightRef.current = true
    setResending(true)
    setError('')
    try {
      await startPhoneSignIn(phoneNumber)
      const masked = maskPhoneNumber(phoneNumber)
      savePendingPhone(phoneNumber, masked, returnTo, pending.loginIntent)
      setMaskedPhone(masked)
      setToast({ tone: 'success', message: 'A new OTP has been sent.' })
      setCooldown(30)
      setOtp('')
    } catch (err) {
      setToast({ tone: 'error', message: err?.message || 'Unable to resend OTP.' })
      setError(err?.message || 'Unable to resend OTP.')
    } finally {
      setResending(false)
      resendInFlightRef.current = false
    }
  }

  function handleEditPhone() {
    const phoneToEdit = phoneNumber
    const loginIntent = pending.loginIntent
    setOtp('')
    setError('')
    setSuccess('')
    resetPhoneSignIn()
    clearPendingPhone()
    navigate('/login', { replace: true, state: { from: returnTo, editPhoneNumber: phoneToEdit, loginIntent } })
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(125,211,252,0.16),_transparent_26%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.14),_transparent_30%),linear-gradient(180deg,#030712_0%,#07111d_46%,#081321_100%)] text-white">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid w-full gap-6 lg:grid-cols-[0.95fr_1.05fr] lg:gap-8">
          <motion.section
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl backdrop-blur-2xl sm:p-8"
          >
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.26em] text-cyan-100">
              <ShieldAlert className="h-4 w-4" />
              Step 2 of 2
            </div>

            <h1 className="mt-5 text-3xl font-black tracking-[-0.05em] sm:text-4xl">Enter the OTP</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300 sm:text-base">
              We sent a 6-digit code to <span className="font-semibold text-white">{maskedPhone || maskPhoneNumber(phoneNumber)}</span>.
            </p>

            <div className="mt-7 grid gap-3 sm:grid-cols-2">
              <StatusCard title="Phone number" value={maskedPhone || maskPhoneNumber(phoneNumber)} icon={Smartphone} />
              <StatusCard title="Cooldown" value={<Countdown seconds={cooldown} />} icon={RefreshCw} />
            </div>

            <div className="mt-7 rounded-3xl border border-white/10 bg-black/20 p-4 text-sm text-slate-300">
              You can paste the full code, use backspace to move between digits, and the form will auto-verify once all digits are filled.
            </div>

            <button
              type="button"
              onClick={handleEditPhone}
              className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-cyan-200 transition hover:text-cyan-100"
            >
              <ArrowLeft className="h-4 w-4" />
              Edit phone number
            </button>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            className="rounded-[2rem] border border-white/10 bg-[#09131f]/90 p-6 shadow-2xl backdrop-blur-2xl sm:p-8"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">Verification</div>
                <h2 className="mt-2 text-2xl font-bold tracking-[-0.04em]">Type the one-time code</h2>
              </div>
              <div className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.2em] text-slate-300">
                {pending.loginIntent === 'admin' ? 'Admin request' : 'Citizen request'}
              </div>
            </div>

            <form
              className="mt-8 space-y-6"
              onSubmit={(event) => {
                event.preventDefault()
                void handleVerify()
              }}
            >
              <OTPInput value={otp} onChange={setOtp} disabled={verifying} />

              {error ? (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100"
                >
                  {error}
                </motion.div>
              ) : null}

              {success ? (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100"
                >
                  {success}
                </motion.div>
              ) : null}

              {accessDecision === 'citizen-admin-blocked' ? (
                <div className="rounded-2xl border border-amber-300/25 bg-amber-400/10 px-4 py-4 text-sm text-amber-50">
                  <div className="font-semibold">Administrator access required. Your account is registered as a Citizen.</div>
                  <button type="button" onClick={() => navigate('/', { replace: true })} className="mt-3 rounded-xl bg-amber-200 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-100">Continue to Citizen Dashboard</button>
                </div>
              ) : null}

              {accessDecision !== 'citizen-admin-blocked' ? <div className="flex flex-col gap-3 sm:flex-row">
                <VerifyButton
                  loading={verifying}
                  disabled={otp.length !== 6}
                  className="flex-1 bg-gradient-to-r from-cyan-400 to-emerald-400 text-slate-950 shadow-lg shadow-cyan-500/20 hover:brightness-110"
                >
                  Verify and continue
                </VerifyButton>

                <button
                  type="button"
                  onClick={handleResend}
                  disabled={cooldown > 0 || resending}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${resending ? 'animate-spin' : ''}`} />
                  Resend OTP
                </button>
              </div> : null}

              <div className="rounded-3xl border border-white/10 bg-black/20 p-4 text-sm text-slate-300">
                <div className="flex items-start gap-3">
                  <Sparkles className="mt-0.5 h-4 w-4 text-cyan-200" />
                  <div>
                    <div className="font-semibold text-white">Security reminder</div>
                    <p className="mt-1 leading-6">
                      OTPs expire automatically, resend is rate-limited, and the dashboard will only load after the backend returns a signed JWT.
                    </p>
                  </div>
                </div>
              </div>
            </form>
          </motion.section>
        </div>
      </div>

      <AnimatePresence>
        {toast ? (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            className={`fixed bottom-5 right-5 z-50 max-w-sm rounded-2xl border px-4 py-3 text-sm shadow-2xl backdrop-blur-xl ${
              toast.tone === 'success'
                ? 'border-emerald-400/20 bg-emerald-500/15 text-emerald-50'
                : 'border-rose-400/20 bg-rose-500/15 text-rose-50'
            }`}
          >
            {toast.message}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

function StatusCard({ title, value, icon: Icon }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-black/20 p-4">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-slate-400">
        <Icon className="h-3.5 w-3.5 text-cyan-200" />
        {title}
      </div>
      <div className="mt-2 text-sm font-semibold text-white">{value}</div>
    </div>
  )
}
