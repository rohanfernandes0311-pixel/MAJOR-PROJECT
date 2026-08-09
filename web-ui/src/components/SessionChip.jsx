import { LogOut, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { clearPendingPhone, maskPhoneNumber } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'

export default function SessionChip() {
  const navigate = useNavigate()
  const { authenticated, profile, signOut } = useAuth()

  if (!authenticated) return null

  const maskedPhone = profile?.phone_number_masked || maskPhoneNumber(profile?.phone_number || '')

  async function handleLogout() {
    clearPendingPhone()
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="fixed right-4 top-4 z-50 rounded-full border border-white/10 bg-[#09131f]/90 px-3 py-2 shadow-2xl backdrop-blur-xl sm:right-6 sm:top-6">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-xs text-slate-300">
          <ShieldCheck className="h-4 w-4 text-cyan-200" />
          <span className="hidden sm:inline">Authenticated</span>
          <span className="font-semibold text-white">{maskedPhone || 'Session active'}</span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:bg-white/10"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </div>
  )
}
