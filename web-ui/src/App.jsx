import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import AuthGate from './components/AuthGate'
import ProtectedRoute from './authentication/ProtectedRoute'
import SessionChip from './components/SessionChip'
import Login from './pages/Login'
import OTP from './pages/OTP'
import Public from './pages/Public'
import DemoMode from './pages/DemoMode'

const Admin = lazy(() => import('./pages/Admin'))
const SimulationDemo = lazy(() => import('./pages/SimulationDemo'))

function RouteLoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050b14] text-slate-100">
      <div className="rounded-3xl border border-white/10 bg-white/5 px-6 py-5 shadow-2xl backdrop-blur-xl">
        <div className="text-xs uppercase tracking-[0.28em] text-slate-400">LandSense</div>
        <div className="mt-2 text-lg font-semibold">Loading page...</div>
        <div className="mt-4 h-1.5 w-64 overflow-hidden rounded-full bg-white/10">
          <div className="h-full w-1/2 rounded-full bg-cyan-300/80 animate-pulse" />
        </div>
      </div>
    </div>
  )
}

export default function App(){
  return (
    <BrowserRouter>
      <AuthProvider>
        <SessionChip />
        <Suspense fallback={<RouteLoadingFallback />}>
          <Routes>
            <Route path="/login" element={<Login/>} />
            <Route path="/frontend/login" element={<Login/>} />
            <Route path="/otp" element={<OTP/>} />
            <Route path="/frontend/otp" element={<OTP/>} />

            <Route path="/" element={<AuthGate><Public/></AuthGate>} />
            <Route path="/frontend" element={<AuthGate><Public/></AuthGate>} />
            <Route path="/frontend/index.html" element={<AuthGate><Public/></AuthGate>} />
            <Route path="/admin" element={<ProtectedRoute role="Admin"><Admin/></ProtectedRoute>} />
            <Route path="/admin/simulation" element={<ProtectedRoute role="Admin"><SimulationDemo/></ProtectedRoute>} />
            <Route path="/frontend/admin/simulation" element={<ProtectedRoute role="Admin"><SimulationDemo/></ProtectedRoute>} />
            <Route path="/admin/simulation/demo" element={<ProtectedRoute role="Admin"><SimulationDemo/></ProtectedRoute>} />
            <Route path="/frontend/admin/simulation/demo" element={<ProtectedRoute role="Admin"><SimulationDemo/></ProtectedRoute>} />
            <Route path="/frontend/admin" element={<ProtectedRoute role="Admin"><Admin/></ProtectedRoute>} />
            <Route path="/demo" element={<ProtectedRoute role="Admin"><DemoMode/></ProtectedRoute>} />
            <Route path="/frontend/demo" element={<ProtectedRoute role="Admin"><DemoMode/></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
