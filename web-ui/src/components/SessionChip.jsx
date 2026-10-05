import { LogOut } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { clearPendingPhone, maskPhoneNumber } from '../auth/authClient'
import { useAuth } from '../auth/AuthProvider'

export default function SessionChip() {
  const navigate = useNavigate()
  const location = useLocation()
  const { authenticated, profile, signOut } = useAuth()

  if (!authenticated || location.pathname === '/admin' || location.pathname === '/frontend/admin') return null

  const maskedPhone = profile?.phone_number_masked || maskPhoneNumber(profile?.phone_number || '')

  async function handleLogout() {
    clearPendingPhone()
    await signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="session-chip fixed right-4 top-3 z-50 border-l border-[#dfe5df] bg-white pl-3 sm:right-6">
      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-2 text-xs text-slate-500 md:flex">
          <span className="font-medium text-slate-700">{maskedPhone || 'Session active'}</span>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Log out</span>
        </button>
      </div>
    </div>
  )
}
