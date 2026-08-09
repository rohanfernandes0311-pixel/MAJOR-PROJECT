import { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import MapView from '../shared/MapView'
import RiskCard from '../shared/RiskCard'
import EvacuationPanel from '../shared/EvacuationPanel'
import { BarChart3, ChevronLeft, Home, LayoutDashboard, LogOut, Settings2, User } from 'lucide-react'
import { Sidebar, SidebarBody, SidebarLink } from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'
import {
  clearOfflineEmergencyAlert,
  isDangerState,
  loadOfflineEmergencyAlert,
  persistOfflineEmergencyAlert
} from '../shared/offlineEmergencyAlertStore'
import { getStoredAuth } from '../auth/authClient'

const FALLBACK_LOCATION = { lat: 18.55, lng: 73.9 }
const API_BASE = window.location.origin

const STORAGE = {
  uid: 'landsense_uid',
  alerts: 'landsense_alerts_enabled',
  lastRiskUi: 'landsense_last_risk_ui',
  lastRiskRaw: 'landsense_last_risk_raw',
  lastUpdated: 'landsense_last_updated'
}

function getSafeZoneCenter(features) {
  const safeCandidates = features.filter((f) => {
    const level = String(f?.properties?.risk_level || '').toUpperCase()
    return level === 'SAFE' || level === 'LOW'
  })
  const target = safeCandidates.length ? safeCandidates[0] : features[0]
  const coords = target?.geometry?.coordinates?.[0] || []
  if (!coords.length) return null
  const sum = coords.reduce((acc, pair) => ({ lat: acc.lat + pair[1], lng: acc.lng + pair[0] }), { lat: 0, lng: 0 })
  return [sum.lat / coords.length, sum.lng / coords.length]
}

function getRiskLabel(risk) {
  if (risk === 'SAFE') return 'SAFE'
  if (risk === 'WARNING') return 'WARNING'
  if (risk === 'HIGH' || risk === 'CRITICAL' || risk === 'HIGH RISK') return 'EXTREME'
  return risk
}

function getBannerConfig(finalRisk, recommendation) {
  const toneMap = { SAFE: 'safe', WARNING: 'warning' }
  return {
    tone: toneMap[finalRisk] || 'danger',
    title:
      finalRisk === 'SAFE'
        ? 'Safety monitoring is active'
        : finalRisk === 'WARNING'
          ? 'Landslide conditions may be changing'
          : 'High landslide risk detected',
    body: recommendation
  }
}

function getRecommendation(finalRisk) {
  if (finalRisk === 'HIGH' || finalRisk === 'CRITICAL' || finalRisk === 'HIGH RISK') return 'Evacuation recommended'
  if (finalRisk === 'WARNING') return 'Stay alert and avoid hilly routes'
  return 'Conditions look stable for now'
}

function normalizeRisk(raw) {
  return String(raw || 'UNKNOWN').trim().toUpperCase()
}

function isEvacuationRisk(rawRisk) {
  const risk = normalizeRisk(rawRisk)
  return risk === 'HIGH' || risk === 'CRITICAL'
}

function toUiRisk(rawRisk) {
  const risk = normalizeRisk(rawRisk)
  if (risk === 'LOW' || risk === 'SAFE') return 'SAFE'
  if (risk === 'MEDIUM' || risk === 'WARNING') return 'WARNING'
  if (risk === 'HIGH' || risk === 'CRITICAL') return 'HIGH RISK'
  return '--'
}

function nextDelayMs() {
  return Math.floor(10000 + Math.random() * 10000)
}

function nowTimeText() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function geolocationErrorToText(err) {
  if (!err) return "Couldn't access location."
  if (err.code === 1) return 'Location permission is off.'
  if (err.code === 2) return 'Location is unavailable.'
  if (err.code === 3) return 'Location timed out.'
  return "Couldn't access location."
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Location is not available on this device.'))
      return
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 5000
    })
  })
}

function getOrCreateUid() {
  const existing = (localStorage.getItem(STORAGE.uid) || '').trim()
  if (existing) return existing
  const uid = `ls-${Math.random().toString(16).slice(2)}-${Date.now().toString(16)}`
  localStorage.setItem(STORAGE.uid, uid)
  return uid
}

async function fetchJson(path, options = {}) {
  const token = getStoredAuth().token
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    ...options
  })
  if (!resp.ok) {
    const txt = await resp.text()
    const err = new Error(txt || 'Request failed')
    err.status = resp.status
    throw err
  }
  return resp.json()
}

function riskBodyText(uiRisk) {
  if (uiRisk === 'HIGH RISK') return 'High risk detected. Move to a safer area immediately.'
  if (uiRisk === 'WARNING') return 'Risk is rising. Stay alert and be ready to move.'
  if (uiRisk === 'SAFE') return 'Area conditions look stable.'
  return 'Please check your safety status.'
}

function friendlyLocation(raw) {
  const t = (raw || '').toLowerCase()
  if (t.includes('active')) return 'Monitoring nearby conditions'
  if (t.includes('ready')) return 'Monitoring ready'
  if (t.includes('finding') || t.includes('look')) return 'Finding your location...'
  if (t.includes('off') || t.includes('denied')) return 'Location is off'
  if (t.includes('not available')) return 'Location unavailable'
  if (t.includes('not shared')) return 'Location not shared'
  if (t.includes('timed out')) return 'Location timed out'
  return 'Location not shared'
}

function WeatherCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">{label}</div>
      <div className="mt-1 text-sm font-semibold text-white">{value}</div>
    </div>
  )
}

export default function Public() {
  const [status, setStatus] = useState({
    risk: '--',
    confidence: 0,
    rainfall: 0,
    soil_moisture: 45,
    deformation: 5,
    recommendation: 'Monitoring is active',
    alert: 'Safety monitoring is ready'
  })
  const [zones, setZones] = useState([])
  const [location, setLocation] = useState(null)
  const [route, setRoute] = useState(null)
  const [evacuation, setEvacuation] = useState(null)
  const [weather, setWeather] = useState(null)
  const [banner, setBanner] = useState({
    tone: 'safe',
    title: 'Safety monitoring is ready',
    body: 'We are checking nearby conditions in real time.'
  })
  const [loading, setLoading] = useState(false)
  const [monitoring, setMonitoring] = useState(false)
  const [alertsEnabled, setAlertsEnabled] = useState(localStorage.getItem(STORAGE.alerts) === '1')
  const [locationStatus, setLocationStatus] = useState('Location not shared')
  const [statusText, setStatusText] = useState('Ready to protect you.')
  const [lastUpdate, setLastUpdate] = useState(localStorage.getItem(STORAGE.lastUpdated) || 'Waiting')
  const [offline, setOffline] = useState(!navigator.onLine)
  const [simulationState, setSimulationState] = useState({ enabled: false, effective_risk: 'LOW', scenario_name: '' })
  const [offlineEmergency, setOfflineEmergency] = useState(null)
  const [offlineRestored, setOfflineRestored] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const uidRef = useRef('')
  const timerRef = useRef(null)
  const monitoringRef = useRef(false)
  const deferredInstallPromptRef = useRef(null)
  const dashboardRef = useRef(null)
  const mapRef = useRef(null)
  const alertsRef = useRef(null)

  const navItems = [
    { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { key: 'home', label: 'Home', icon: Home },
    { key: 'analytics', label: 'Analytics', icon: BarChart3 },
    { key: 'profile', label: 'Profile', icon: User },
    { key: 'settings', label: 'Settings', icon: Settings2 },
    { key: 'logout', label: 'Logout', icon: LogOut }
  ]

  const updateRoute = useCallback(async (zonesData, currentLocation) => {
    if (!zonesData.length || !currentLocation) return

    try {
      const primaryZoneCenter = getSafeZoneCenter(zonesData)
      if (primaryZoneCenter) {
        const routeResp = await fetchJson('/route-safe', {
          method: 'POST',
          body: JSON.stringify({
            start_latitude: currentLocation.lat,
            start_longitude: currentLocation.lng,
            end_latitude: primaryZoneCenter[0],
            end_longitude: primaryZoneCenter[1]
          })
        })
        const points = Array.isArray(routeResp?.route) ? routeResp.route : []
        if (points.length >= 2) {
          const start = [Number(points[0].lat), Number(points[0].lon)]
          const endPoint = points[points.length - 1]
          const end = [Number(endPoint.lat), Number(endPoint.lon)]
          setRoute({ start, end })
          return
        }
      }
    } catch {
      // Fallback to direct line if route-safe is unavailable for this geometry.
    }

    const center = getSafeZoneCenter(zonesData)
    if (center) setRoute({ start: [currentLocation.lat, currentLocation.lng], end: center })
  }, [])

  const showLocalAlert = useCallback(
    async (uiRisk) => {
      if (!alertsEnabled) return
      if (!('serviceWorker' in navigator)) return
      if (!('Notification' in window)) return
      if (Notification.permission !== 'granted') return

      const reg = await navigator.serviceWorker.ready
      await reg.showNotification('Landslide Alert', {
        body: riskBodyText(uiRisk),
        tag: 'landsense-risk',
        renotify: true,
        data: { url: '/', risk: uiRisk }
      })
    },
    [alertsEnabled]
  )

  const tryPredict = useCallback(async (lat, lng) => {
    const minimal = { latitude: lat, longitude: lng }
    try {
      return await fetchJson('/predict', { method: 'POST', body: JSON.stringify(minimal) })
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405 || err.status === 422)) {
        const fallback = {
          latitude: lat,
          longitude: lng,
          deformation_mm: 5.0,
          velocity_mm_yr: 12.0,
          coherence: 0.8,
          slope_deg: 24.0,
          soil_moisture_pct: 45.0,
          elevation_m: 900.0,
          ndvi: 0.4,
          model: 'ensemble'
        }
        return await fetchJson('/predict-risk', { method: 'POST', body: JSON.stringify(fallback) })
      }
      throw err
    }
  }, [])

  const checkSafetyOnce = useCallback(async () => {
    setLoading(true)
    setStatusText('Analyzing nearby conditions...')
    setLocationStatus(friendlyLocation('finding'))

    try {
      let pos
      try {
        pos = await getCurrentPosition()
      } catch (geoErr) {
        setLocationStatus(friendlyLocation('not available'))
        setStatusText(geolocationErrorToText(geoErr))
        return
      }

      const lat = Number(pos.coords.latitude.toFixed(6))
      const lng = Number(pos.coords.longitude.toFixed(6))
      const currentLocation = { lat, lng }
      setLocation(currentLocation)
      setLocationStatus(friendlyLocation('active'))

      let locationUpdate = null
      try {
        locationUpdate = await fetchJson('/location-update', {
          method: 'POST',
          body: JSON.stringify({
            user_id: uidRef.current,
            location_name: 'Mobile User',
            latitude: lat,
            longitude: lng
          })
        })
      } catch {
        // Prediction endpoint may still succeed.
      }

      let prediction = null
      try {
        prediction = await tryPredict(lat, lng)
      } catch {
        // location-update may already contain final_risk.
      }

      const rawRisk =
        locationUpdate?.final_risk ||
        prediction?.final_risk ||
        prediction?.risk_level ||
        prediction?.risk ||
        prediction?.prediction?.risk_label ||
        prediction?.prediction?.riskLabel ||
        'UNKNOWN'

      const simulation = locationUpdate?.simulation || { enabled: false, effective_risk: 'LOW', scenario_name: '' }
      setSimulationState(simulation)
      const weatherContext = locationUpdate?.weather || prediction?.weather || null
      setWeather(weatherContext)

      const uiRisk = toUiRisk(rawRisk)
      const hasFreshRisk = uiRisk !== '--'

      if (hasFreshRisk) {
        const normalizedRaw = normalizeRisk(rawRisk)
        const finalRisk = uiRisk === 'HIGH RISK' ? 'HIGH' : uiRisk
        const recommendation = getRecommendation(finalRisk)

        const rainfall =
          locationUpdate?.rainfall?.rainfall_mm ??
          prediction?.rainfall?.rainfall_mm ??
          status.rainfall
        const evacuationGuidance = locationUpdate?.evacuation || prediction?.evacuation || null

        setStatus({
          risk: uiRisk,
          confidence: Number(prediction?.prediction?.confidence ?? locationUpdate?.ml_prediction?.confidence ?? status.confidence ?? 0),
          rainfall,
          soil_moisture: Number(
            prediction?.prediction?.feature_values?.soil_moisture_pct ??
              locationUpdate?.ml_prediction?.feature_values?.soil_moisture_pct ??
              status.soil_moisture
          ),
          deformation: Number(
            prediction?.prediction?.feature_values?.deformation_mm ??
              locationUpdate?.ml_prediction?.feature_values?.deformation_mm ??
              status.deformation
          ),
          recommendation,
          alert: recommendation
        })

        setBanner(getBannerConfig(finalRisk, recommendation))
        setEvacuation(isEvacuationRisk(finalRisk) ? evacuationGuidance : null)
        const updatedAt = nowTimeText()
        setLastUpdate(updatedAt)
        setStatusText('Updated just now')
        localStorage.setItem(STORAGE.lastRiskUi, uiRisk)
        localStorage.setItem(STORAGE.lastRiskRaw, normalizedRaw)
        localStorage.setItem(STORAGE.lastUpdated, updatedAt)

        if (isDangerState(uiRisk, simulation.enabled)) {
          const emergencySnapshot = persistOfflineEmergencyAlert({
            risk_level: normalizedRaw,
            ui_risk: uiRisk,
            recommendation,
            banner_title: getBannerConfig(finalRisk, recommendation).title,
            evacuation_warning: recommendation,
            danger_state: true,
            simulation,
            location: currentLocation,
            timestamp: new Date().toISOString()
          })
          setOfflineEmergency(emergencySnapshot)
          setOfflineRestored(false)
        } else {
          clearOfflineEmergencyAlert()
          setOfflineEmergency(null)
          setOfflineRestored(false)
          setEvacuation(null)
          setRoute(null)
        }

        if (uiRisk === 'HIGH RISK' || uiRisk === 'WARNING') {
          await showLocalAlert(uiRisk)
          if ('speechSynthesis' in window && alertsEnabled) {
            const utterance = new SpeechSynthesisUtterance(`${getBannerConfig(finalRisk, recommendation).title}. ${recommendation}.`)
            utterance.rate = 0.92
            utterance.pitch = 1
            utterance.lang = 'en-US'
            window.speechSynthesis.cancel()
            window.speechSynthesis.speak(utterance)
          }
        }
      } else {
        // Restore the latest persisted emergency warning when live refresh fails.
        setWeather(null)
        const cached = loadOfflineEmergencyAlert()
        if (cached) {
          setOfflineEmergency(cached)
          setOfflineRestored(true)
          setStatus((prev) => ({
            ...prev,
            risk: cached.ui_risk || prev.risk,
            recommendation: cached.recommendation || prev.recommendation,
            alert: cached.evacuation_warning || prev.alert
          }))
          setBanner({
            tone: 'danger',
            title: cached.banner_title || 'High landslide risk detected',
            body: cached.recommendation || 'Evacuation recommended'
          })
          setStatusText('Using persisted emergency warning')
        } else {
          setStatusText(navigator.onLine ? "Couldn't update right now." : 'Using latest saved safety update')
        }
        setEvacuation(null)
        setRoute(null)
      }

      if (isEvacuationRisk(uiRisk) && zones.length) {
        await updateRoute(zones, currentLocation)
      } else {
        setRoute(null)
      }
    } finally {
      setLoading(false)
    }
  }, [alertsEnabled, showLocalAlert, status, tryPredict, updateRoute, zones])

  const stopMonitoring = useCallback(() => {
    monitoringRef.current = false
    setMonitoring(false)
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setStatusText('Monitoring paused')
  }, [])

  const scrollToSection = useCallback(
    (key) => {
      if (key === 'dashboard' || key === 'home') {
        dashboardRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
        return
      }
      if (key === 'analytics') {
        mapRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
        return
      }
      if (key === 'profile' || key === 'settings') {
        alertsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
        return
      }
      if (key === 'logout') {
        stopMonitoring()
        setAlertsEnabled(false)
        localStorage.removeItem(STORAGE.alerts)
      }
    },
    [stopMonitoring]
  )

  const monitoringLoop = useCallback(async () => {
    if (!monitoringRef.current) return
    await checkSafetyOnce()
    if (!monitoringRef.current) return
    timerRef.current = setTimeout(monitoringLoop, nextDelayMs())
  }, [checkSafetyOnce])

  const startMonitoring = useCallback(async () => {
    if (monitoringRef.current) return
    monitoringRef.current = true
    setMonitoring(true)
    setStatusText('Monitoring nearby conditions')

    if (deferredInstallPromptRef.current) {
      try {
        await deferredInstallPromptRef.current.prompt()
      } catch {
        // Ignore install prompt failures.
      } finally {
        deferredInstallPromptRef.current = null
      }
    }

    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }

    await monitoringLoop()
  }, [monitoringLoop])

  const fetchVapidPublicKey = useCallback(async () => {
    const candidates = ['/vapid-public-key', '/push-public-key', '/public-key', '/vapidPublicKey']
    for (const path of candidates) {
      try {
        const resp = await fetch(`${API_BASE}${path}`)
        if (!resp.ok) continue
        const txt = (await resp.text()).trim()
        if (txt) return txt
      } catch {
        // Try next endpoint.
      }
    }
    return null
  }, [])

  const urlBase64ToUint8Array = useCallback((base64String) => {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
    const rawData = atob(base64)
    const arr = new Uint8Array(rawData.length)
    for (let i = 0; i < rawData.length; i += 1) arr[i] = rawData.charCodeAt(i)
    return arr
  }, [])

  const enableAlerts = useCallback(async () => {
    if (!('Notification' in window)) {
      setStatusText("Alerts aren't supported on this device.")
      return
    }

    const perm = await Notification.requestPermission()
    if (perm !== 'granted') {
      setStatusText('Alerts are off')
      return
    }

    if (!('serviceWorker' in navigator)) {
      setStatusText("Alerts aren't available on this device.")
      return
    }

    let registration
    try {
      registration = await navigator.serviceWorker.register('/sw.js')
      try {
        await registration.update()
      } catch {
        // Ignore transient update errors.
      }
    } catch {
      setStatusText("Couldn't enable alerts right now.")
      return
    }

    let subscription = null
    try {
      subscription = await registration.pushManager.getSubscription()
      if (!subscription) {
        const vapidKey = await fetchVapidPublicKey()
        if (vapidKey) {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey)
          })
        }
      }
    } catch {
      // Push not configured server-side.
    }

    try {
      await fetchJson('/subscribe', {
        method: 'POST',
        body: JSON.stringify({ alert_enabled: true, user_id: uidRef.current, subscription })
      })
    } catch {
      // Optional endpoint in some deployments.
    }

    setAlertsEnabled(true)
    localStorage.setItem(STORAGE.alerts, '1')
    setStatusText('Alerts are on')

    try {
      const reg = await navigator.serviceWorker.ready
      await reg.showNotification('Landslide Alert', {
        body: "Alerts are ready. You'll be warned here if risk rises.",
        tag: 'landsense-enabled',
        data: { url: '/' }
      })
    } catch {
      // Notification may fail when OS suppresses duplicates.
    }
  }, [fetchVapidPublicKey, urlBase64ToUint8Array])

  useEffect(() => {
    let mounted = true

    async function fetchZones() {
      try {
        const res = await fetch('/zones')
        if (!res.ok) return
        const json = await res.json()
        const features = Array.isArray(json.features) ? json.features : []
        if (mounted) setZones(features)
      } catch {
        // Keep rendering with default state.
      }
    }

    fetchZones()
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    uidRef.current = getOrCreateUid()

    const savedUiRisk = (localStorage.getItem(STORAGE.lastRiskUi) || '').trim()
    const initialRisk = savedUiRisk && savedUiRisk !== '--' ? savedUiRisk : '--'
    if (initialRisk !== '--') {
      const normalized = initialRisk === 'HIGH RISK' ? 'HIGH' : initialRisk
      const recommendation = getRecommendation(normalized)
      setStatus((prev) => ({ ...prev, risk: initialRisk, recommendation, alert: recommendation }))
      setBanner(getBannerConfig(normalized, recommendation))
    }

    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions
        .query({ name: 'geolocation' })
        .then((res) => {
          if (res.state === 'granted') setLocationStatus(friendlyLocation('ready'))
          else if (res.state === 'denied') setLocationStatus(friendlyLocation('off'))
          else setLocationStatus(friendlyLocation('not shared'))
        })
        .catch(() => setLocationStatus(friendlyLocation('not shared')))
    }

    const onOnline = () => {
      setOffline(false)
      setOfflineRestored(false)
    }
    const onOffline = () => {
      setOffline(true)
      const cached = loadOfflineEmergencyAlert()
      if (!cached) return
      setOfflineEmergency(cached)
      setOfflineRestored(true)
      if (!status.risk || status.risk === '--') {
        setStatus((prev) => ({
          ...prev,
          risk: cached.ui_risk || prev.risk,
          recommendation: cached.recommendation || prev.recommendation,
          alert: cached.evacuation_warning || prev.alert
        }))
      }
      if (cached.banner_title || cached.recommendation) {
        setBanner({
          tone: 'danger',
          title: cached.banner_title || 'High landslide risk detected',
          body: cached.recommendation || 'Evacuation recommended'
        })
      }
    }

    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    const onBeforeInstallPrompt = (e) => {
      e.preventDefault()
      deferredInstallPromptRef.current = e
    }

    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)

    if ('serviceWorker' in navigator) {
      let refreshing = false
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (refreshing) return
        refreshing = true
        window.location.reload()
      })

      navigator.serviceWorker
        .register('/sw.js')
        .then((reg) => reg.update())
        .catch(() => {
          // Keep app running when SW registration fails.
        })
    }

    const cached = loadOfflineEmergencyAlert()
    if (cached) {
      setOfflineEmergency(cached)
      if (offline) setOfflineRestored(true)
      if (!navigator.onLine) {
        setStatus((prev) => ({
          ...prev,
          risk: cached.ui_risk || prev.risk,
          recommendation: cached.recommendation || prev.recommendation,
          alert: cached.evacuation_warning || prev.alert
        }))
        setBanner({
          tone: 'danger',
          title: cached.banner_title || 'High landslide risk detected',
          body: cached.recommendation || 'Evacuation recommended'
        })
      }
    }

    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      window.speechSynthesis.cancel()
    }
  }, [])

  useEffect(() => {
    if (!isEvacuationRisk(status.risk)) {
      setRoute(null)
      setEvacuation(null)
      return
    }

    if (zones.length && location) {
      updateRoute(zones, location)
    }
  }, [zones, location, status.risk, updateRoute])

  useEffect(() => {
    if (simulationState.enabled) return
    if (status.risk === '--') return
    if (isDangerState(status.risk, false)) return
    clearOfflineEmergencyAlert()
    setOfflineEmergency(null)
    setOfflineRestored(false)
  }, [status.risk, simulationState.enabled])

  useEffect(() => {
    if (simulationState.enabled) return
    if (!offlineEmergency?.simulation?.enabled) return
    clearOfflineEmergencyAlert()
    setOfflineEmergency(null)
    setOfflineRestored(false)
  }, [offlineEmergency, simulationState.enabled])

  const riskLabel = useMemo(() => getRiskLabel(status.risk), [status.risk])

  const dismissOfflineEmergency = useCallback(() => {
    clearOfflineEmergencyAlert()
    setOfflineEmergency(null)
    setOfflineRestored(false)
  }, [])

  const speakBanner = () => {
    if (!('speechSynthesis' in window)) return
    const text = `${banner.title}. ${banner.body}.`
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.92
    utterance.pitch = 1
    utterance.lang = 'en-US'
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utterance)
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.12),_transparent_28%),linear-gradient(180deg,_#06111b_0%,_#091421_100%)] px-4 py-4 text-white sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px] lg:grid lg:grid-cols-[290px_minmax(0,1fr)] lg:gap-6">
        <aside className="mb-4 overflow-hidden rounded-[28px] border border-white/8 bg-[#0b1522]/95 shadow-[0_20px_80px_rgba(3,7,18,0.45)] backdrop-blur xl:sticky xl:top-6 xl:mb-0 xl:h-[calc(100vh-3rem)]">
          <Sidebar open={sidebarOpen} setOpen={setSidebarOpen}>
            <SidebarBody
              className={cn(
                'justify-between gap-10 bg-transparent text-white',
                'w-full px-0 py-0'
              )}
            >
              <div className="flex h-full flex-1 flex-col overflow-hidden px-5 py-5">
                <div className="flex items-center justify-between border-b border-white/8 pb-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#22c1ff_0%,#7c3aed_55%,#c026d3_100%)] text-sm font-black text-white shadow-lg shadow-cyan-500/20">
                      L
                    </div>
                    <div>
                      <div className="text-xl font-bold tracking-tight text-white">Land Sense</div>
                      <div className="text-xs uppercase tracking-[0.22em] text-slate-400">Command Center</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSidebarOpen((current) => !current)}
                    className="flex h-9 w-9 items-center justify-center rounded-full border border-white/8 bg-white/5 text-slate-400"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                </div>

                <nav className="flex-1 py-5">
                  <div className="space-y-2">
                    {navItems.map((item, index) => {
                      const Icon = item.icon
                      const active = index === 0
                      return (
                        <SidebarLink
                          key={item.key}
                          link={{
                            label: item.label,
                            href: '#',
                            icon: (
                              <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${active ? 'bg-white/12' : 'bg-white/5'}`}>
                                <Icon className="h-5 w-5" />
                              </span>
                            )
                          }}
                          className={`group flex items-center justify-between rounded-2xl px-4 py-4 text-left transition ${
                            active
                              ? 'bg-[linear-gradient(135deg,#2563eb_0%,#7c3aed_55%,#c026d3_100%)] text-white shadow-lg shadow-violet-500/20'
                              : 'text-slate-300 hover:bg-white/5 hover:text-white'
                          }`}
                          onClick={(event) => {
                            event.preventDefault()
                            scrollToSection(item.key)
                          }}
                        />
                      )
                    })}
                  </div>

                  <div className="mt-6 rounded-[24px] border border-white/8 bg-[#08101a] p-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[linear-gradient(135deg,#06b6d4_0%,#22c55e_100%)] text-sm font-bold text-white">
                        LS
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-white">LandSense Public View</div>
                        <div className="text-sm text-slate-400">{monitoring ? 'Monitoring nearby conditions' : 'Ready to protect you'}</div>
                      </div>
                    </div>
                    <div className="mt-4 rounded-2xl border border-white/8 bg-white/5 px-3 py-2 text-xs text-slate-300">
                      {alertsEnabled ? 'Alerts are enabled for this device.' : 'Enable alerts to receive live warnings.'}
                    </div>
                  </div>
                </nav>
              </div>
            </SidebarBody>
          </Sidebar>
        </aside>

        <main className="space-y-6">
          {simulationState.enabled ? (
            <div className="mx-auto max-w-screen-xl px-0 pt-0">
          <div className="rounded-2xl border border-amber-300/40 bg-amber-500/15 px-4 py-3 text-sm text-amber-100 shadow-lg">
            <div className="text-xs font-semibold tracking-[0.24em]">⚠ SIMULATION MODE ACTIVE</div>
            <div className="mt-1">
              Emergency simulation is overriding live geofence state ({simulationState.effective_risk || 'HIGH'} risk).
            </div>
          </div>
            </div>
          ) : null}

          {offline ? (
            <div className="mx-auto max-w-screen-xl px-0 pt-0">
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-200">
            Using latest saved safety update while offline.
          </div>
          {offlineRestored ? (
            <div className="mt-3 rounded-2xl border border-amber-300/35 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              ⚠ Offline Emergency Alert Restored
            </div>
          ) : null}
          {offlineEmergency ? (
            <div className="mt-3 rounded-2xl border border-red-300/35 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">Offline emergency snapshot available</div>
                  <div className="mt-1">{offlineEmergency.banner_title || 'Emergency warning persisted for offline safety.'}</div>
                </div>
                <button
                  type="button"
                  onClick={dismissOfflineEmergency}
                  className="rounded-lg border border-red-200/40 bg-red-400/20 px-3 py-1.5 text-xs font-semibold text-red-50"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ) : null}
            </div>
          ) : null}

          <div ref={dashboardRef} className="sticky top-0 z-30 border-b border-white/5 bg-[#07101a]/90 backdrop-blur-xl">
            <div className={`mx-auto max-w-screen-xl px-4 py-3 ${banner.tone === 'danger' ? 'animate-pulse' : ''}`}>
              <div
                className={`rounded-2xl px-4 py-3 shadow-lg ${
                  banner.tone === 'danger'
                    ? 'bg-red-500/15 border border-red-400/30'
                    : banner.tone === 'warning'
                      ? 'bg-orange-500/15 border border-orange-400/25'
                      : 'bg-emerald-500/10 border border-emerald-400/20'
                }`}
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.28em] text-slate-300">Emergency status</div>
                    <div className="text-lg font-semibold">{banner.title}</div>
                    <div className="mt-1 text-sm text-slate-200/90">{banner.body}</div>
                    <div className="mt-2 text-xs text-slate-300">{statusText}</div>
                  </div>
                  <button
                    onClick={speakBanner}
                    className="self-start rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/10"
                  >
                    Voice guidance
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="mx-auto max-w-screen-xl p-4 md:p-6">
            <header className="mb-4 grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
              <div className="rounded-3xl border border-white/8 bg-white/5 p-5 shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm text-slate-300">LandSense</div>
                    <div className="text-2xl font-semibold tracking-tight">Real-time disaster intelligence</div>
                    <div className="mt-1 text-sm text-slate-300">
                      Location-aware landslide safety for public users and emergency teams.
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Location status</div>
                    <div className="mt-1 text-sm font-semibold">{locationStatus}</div>
                    <div className="mt-2 text-xs text-slate-400">Last check: {lastUpdate}</div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-3xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Risk level</div>
                  <div className="mt-2 text-2xl font-bold text-white">{riskLabel}</div>
                </div>
                <div className="rounded-3xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Monitoring</div>
                  <div className="mt-2 text-lg font-bold text-white">{monitoring ? 'Active' : 'Paused'}</div>
                </div>
              </div>
            </header>

            <main className="grid grid-cols-1 gap-4 lg:grid-cols-[0.95fr_1.35fr]">
              <div className="space-y-4" ref={alertsRef}>
                <RiskCard risk={status.risk} confidence={status.confidence} rainfall={status.rainfall} recommendation={status.recommendation} />

                {isEvacuationRisk(status.risk) ? (
                  <EvacuationPanel evacuation={evacuation} weather={weather} risk={status.risk} onReplayGuidance={speakBanner} />
                ) : null}

                {weather ? (
                  <section className="grid grid-cols-2 gap-3 rounded-3xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                    <WeatherCard label="Temperature" value={`${Number(weather.temperature_c || 0).toFixed(1)} °C`} />
                    <WeatherCard label="Humidity" value={`${Number(weather.humidity_pct || 0).toFixed(0)}%`} />
                    <WeatherCard label="Wind speed" value={`${Number(weather.wind_speed_mps || 0).toFixed(1)} m/s`} />
                    <WeatherCard label="Weather" value={`${weather.weather_main || 'Unknown'}${weather.weather_description ? ` • ${weather.weather_description}` : ''}`} />
                  </section>
                ) : null}

                <section className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Rainfall</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.rainfall)} mm</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Soil moisture</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.soil_moisture)}%</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Deformation</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.deformation)} mm</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Action</div>
                    <div className="mt-2 text-sm font-semibold text-slate-100">{status.recommendation}</div>
                  </div>
                </section>

                <section className="rounded-3xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={enableAlerts}
                      disabled={alertsEnabled}
                      className="rounded-xl border border-cyan-300/30 bg-cyan-400/15 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"
                    >
                      {alertsEnabled ? 'Alerts enabled' : 'Turn on alerts'}
                    </button>
                    <button
                      type="button"
                      onClick={startMonitoring}
                      disabled={monitoring || loading}
                      className="rounded-xl border border-emerald-300/30 bg-emerald-400/15 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50"
                    >
                      {loading && monitoring ? 'Checking...' : 'Start monitoring'}
                    </button>
                    <button
                      type="button"
                      onClick={stopMonitoring}
                      disabled={!monitoring}
                      className="rounded-xl border border-red-300/30 bg-red-400/15 px-4 py-2 text-sm font-semibold text-red-100 disabled:opacity-50"
                    >
                      Stop
                    </button>
                  </div>
                </section>

                {simulationState.enabled ? (
                  <section className="rounded-3xl border border-red-300/30 bg-red-500/10 p-4 backdrop-blur-xl">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="text-xs uppercase tracking-[0.24em] text-red-100/80">Emergency drill panel</div>
                        <div className="mt-1 text-lg font-semibold text-red-100">Siren / alarm interface active</div>
                        <div className="mt-1 text-sm text-red-50/90">Follow evacuation guidance and proceed to the highlighted safe route.</div>
                      </div>
                      <button
                        type="button"
                        onClick={speakBanner}
                        className="rounded-xl border border-red-200/35 bg-red-400/20 px-4 py-2 text-sm font-semibold text-red-50"
                      >
                        Replay evacuation guidance
                      </button>
                    </div>
                  </section>
                ) : null}

                <section className="rounded-3xl border border-white/8 bg-white/5 p-4 backdrop-blur-xl">
                  <div className="text-sm font-semibold">Recommendations</div>
                  <div className="mt-3 grid gap-3">
                    <div className="rounded-2xl bg-black/20 px-4 py-3 text-sm text-slate-200">Avoid steep roads and loose slopes.</div>
                    <div className="rounded-2xl bg-black/20 px-4 py-3 text-sm text-slate-200">
                      {isEvacuationRisk(status.risk)
                        ? 'Move toward the highlighted safe zone.'
                        : 'Safe route guidance stays hidden until risk reaches HIGH or CRITICAL.'}
                    </div>
                    <div className="rounded-2xl bg-black/20 px-4 py-3 text-sm text-slate-200">Keep alerts on for live updates.</div>
                  </div>
                </section>
              </div>

              <section ref={mapRef} className="min-h-[60vh] overflow-hidden rounded-[2rem] border border-white/8 bg-[#091521] shadow-2xl">
                <MapView zones={zones} userLocation={location} route={route} risk={status.risk === 'HIGH RISK' ? 'HIGH' : status.risk} />
              </section>
            </main>
          </div>
        </main>
      </div>
    </div>
  )
}
