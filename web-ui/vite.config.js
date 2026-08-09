import path from 'node:path'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const proxiedPaths = [
  '/auth',
  '/send-otp',
  '/verify-otp',
  '/profile',
  '/logout',
  '/zones',
  '/events',
  '/predict',
  '/predict-risk',
  '/location-update',
  '/route-safe',
  '/subscribe',
  '/admin/simulation',
  '/vapid-public-key',
  '/push-public-key',
  '/public-key',
  '/vapidPublicKey',
  '/health'
]

const proxy = Object.fromEntries(
  proxiedPaths.map((path) => [
    path,
    {
      target: backendTarget,
      changeOrigin: true
    }
  ])
)

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy
  }
})
