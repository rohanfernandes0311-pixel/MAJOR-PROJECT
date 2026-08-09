import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

function FullScreenLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050b14] text-slate-100">
      <div className="rounded-3xl border border-white/10 bg-white/5 px-6 py-5 shadow-2xl backdrop-blur-xl">
        <div className="text-xs uppercase tracking-[0.28em] text-slate-400">LandSense</div>
        <div className="mt-2 text-lg font-semibold">Checking access...</div>
        <div className="mt-4 h-1.5 w-64 overflow-hidden rounded-full bg-white/10">
          <div className="h-full w-1/2 rounded-full bg-cyan-300/80 animate-pulse" />
        </div>
      </div>
    </div>
  )
}

export default function AuthGate({ children }) {
  const { ready, authenticated } = useAuth()
  const location = useLocation()

  if (!ready) return <FullScreenLoader />
  if (!authenticated) {
    const from = `${location.pathname}${location.search}`
    return <Navigate to="/login" replace state={{ from }} />
  }

  return children
}
