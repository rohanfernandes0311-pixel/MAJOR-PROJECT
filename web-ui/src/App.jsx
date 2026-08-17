import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import AuthGate from './components/AuthGate'
import ProtectedRoute from './authentication/ProtectedRoute'
import SessionChip from './components/SessionChip'
import Login from './pages/Login'
import OTP from './pages/OTP'
import Public from './pages/Public'
import Admin from './pages/Admin'
import DemoMode from './pages/DemoMode'

export default function App(){
  return (
    <BrowserRouter>
      <AuthProvider>
        <SessionChip />
        <Routes>
          <Route path="/login" element={<Login/>} />
          <Route path="/frontend/login" element={<Login/>} />
          <Route path="/otp" element={<OTP/>} />
          <Route path="/frontend/otp" element={<OTP/>} />

          <Route path="/" element={<AuthGate><Public/></AuthGate>} />
          <Route path="/frontend" element={<AuthGate><Public/></AuthGate>} />
          <Route path="/frontend/index.html" element={<AuthGate><Public/></AuthGate>} />
          <Route path="/admin" element={<ProtectedRoute role="Admin"><Admin/></ProtectedRoute>} />
          <Route path="/frontend/admin" element={<ProtectedRoute role="Admin"><Admin/></ProtectedRoute>} />
          <Route path="/demo" element={<ProtectedRoute role="Admin"><DemoMode/></ProtectedRoute>} />
          <Route path="/frontend/demo" element={<ProtectedRoute role="Admin"><DemoMode/></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
