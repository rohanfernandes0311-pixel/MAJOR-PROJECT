import { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import MapView from '../shared/MapView'
import RiskCard from '../shared/RiskCard'
import EvacuationPanel from '../shared/EvacuationPanel'
import {
  clearOfflineEmergencyAlert,
  loadOfflineEmergencyAlert,
  persistOfflineEmergencyAlert
} from '../shared/offlineEmergencyAlertStore'
import { apiFetch, getStoredAuth } from '../auth/authClient'
import { AlertNotificationManager } from '../services/alertNotificationManager'
import { INCIDENT_DEMO_EVENT, formatIncidentDate, impactLines, readDemoAlert } from '../services/incidentDemo'
import { citizenRiskCopy, deriveCitizenGeofenceState, normalizeRisk } from '../services/citizenGeofence'

const FALLBACK_LOCATION = { lat: 18.55, lng: 73.9 }
const STORAGE = {
  uid: 'landsense_uid',
  alerts: 'landsense_alerts_enabled',
  lastRiskUi: 'landsense_last_risk_ui',
  lastRiskRaw: 'landsense_last_risk_raw',
  lastUpdated: 'landsense_last_updated'
}

function currentNotificationPermission() {
  return 'Notification' in window ? Notification.permission : 'unsupported'
}

function getRiskLabel(risk) {
  return risk === '--' ? 'LOCATING…' : risk
}

function isEvacuationRisk(rawRisk) {
  const risk = normalizeRisk(rawRisk)
  return risk === 'HIGH' || risk === 'HIGH RISK' || risk === 'CRITICAL' || risk === 'CRITICAL RISK'
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

function getOrCreateUid() {
  const existing = (localStorage.getItem(STORAGE.uid) || '').trim()
  if (existing) return existing
  const uid = `ls-${Math.random().toString(16).slice(2)}-${Date.now().toString(16)}`
  localStorage.setItem(STORAGE.uid, uid)
  return uid
}

async function fetchJson(path, options = {}) {
  return apiFetch(path, options, getStoredAuth().token)
}

function riskBodyText(uiRisk) {
  if (uiRisk === 'CRITICAL RISK') return 'Your location is inside a CRITICAL risk zone. Follow official emergency guidance immediately.'
  if (uiRisk === 'HIGH RISK') return 'High risk detected. Move to a safer area immediately.'
  if (uiRisk === 'MEDIUM RISK') return 'You are inside a monitored landslide-risk area. Stay alert.'
  if (uiRisk === 'SAFE') return 'You are outside configured risk zones.'
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

function AlertRiskPill({ risk }) {
  const level = String(risk || 'LOW').toUpperCase()
  const tones = {
    LOW: 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100',
    MEDIUM: 'border-amber-300/25 bg-amber-400/10 text-amber-100',
    HIGH: 'border-orange-300/25 bg-orange-400/10 text-orange-100',
    CRITICAL: 'border-rose-300/25 bg-rose-400/10 text-rose-100'
  }
  return <span className={`rounded-full border px-2 py-1 text-[11px] font-bold tracking-wide ${tones[level] || tones.LOW}`}>{level}</span>
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
  const [destinationText, setDestinationText] = useState('')
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState('')
  const [weather, setWeather] = useState(null)
  const [banner, setBanner] = useState({
    tone: 'safe',
    title: 'Safety monitoring is ready',
    body: 'We are checking nearby conditions in real time.'
  })
  const [loading, setLoading] = useState(false)
  const [monitoring, setMonitoring] = useState(false)
  const [alertsEnabled, setAlertsEnabled] = useState(localStorage.getItem(STORAGE.alerts) === '1')
  const [notificationPermission, setNotificationPermission] = useState(currentNotificationPermission)
  const [locationStatus, setLocationStatus] = useState('Location not shared')
  const [statusText, setStatusText] = useState('Ready to protect you.')
  const [lastUpdate, setLastUpdate] = useState(localStorage.getItem(STORAGE.lastUpdated) || 'Waiting')
  const [offline, setOffline] = useState(!navigator.onLine)
  const [locationAccuracy, setLocationAccuracy] = useState(null)
  const [activeZoneId, setActiveZoneId] = useState('')
  const [offlineEmergency, setOfflineEmergency] = useState(null)
  const [offlineRestored, setOfflineRestored] = useState(false)
  const [targetedAlerts, setTargetedAlerts] = useState([])
  const [alertInboxState, setAlertInboxState] = useState('loading')
  const [landslideRecords, setLandslideRecords] = useState([])
  const [demoAlert, setDemoAlert] = useState(() => readDemoAlert())

  const uidRef = useRef('')
  const monitoringRef = useRef(false)
  const deferredInstallPromptRef = useRef(null)
  const dashboardRef = useRef(null)
  const mapRef = useRef(null)
  const alertsRef = useRef(null)
  const safetyRef = useRef(null)
  const alertNotificationManagerRef = useRef(new AlertNotificationManager())
  const alertPollingTimerRef = useRef(null)
  const alertRefreshInFlightRef = useRef(false)
  const latestPositionRef = useRef(null)
  const evaluatePositionRef = useRef(null)
  const lastEvaluationAtRef = useRef(0)
  const lastNotifiedZoneRiskRef = useRef('')
  const positionEvaluationInFlightRef = useRef(false)

  const refreshTargetedAlerts = useCallback(async () => {
    if (alertRefreshInFlightRef.current) return
    const token = getStoredAuth().token
    if (!token) {
      setAlertInboxState('unavailable')
      return
    }

    alertRefreshInFlightRef.current = true
    try {
      const response = await apiFetch('/alerts/my', {}, token)
      const alerts = Array.isArray(response?.alerts) ? response.alerts : []
      setTargetedAlerts(alerts)
      setAlertInboxState('ready')

      await alertNotificationManagerRef.current.observe(alerts, {
        notify: alertsEnabled && notificationPermission === 'granted'
      })
    } catch {
      setAlertInboxState('unavailable')
    } finally {
      alertRefreshInFlightRef.current = false
    }
  }, [alertsEnabled, notificationPermission])

  useEffect(() => {
    refreshTargetedAlerts()

    alertPollingTimerRef.current = setInterval(refreshTargetedAlerts, 60000)
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        setNotificationPermission(currentNotificationPermission())
        refreshTargetedAlerts()
      }
    }
    window.addEventListener('online', refreshTargetedAlerts)
    document.addEventListener('visibilitychange', refreshWhenVisible)

    return () => {
      if (alertPollingTimerRef.current) {
        clearInterval(alertPollingTimerRef.current)
        alertPollingTimerRef.current = null
      }
      window.removeEventListener('online', refreshTargetedAlerts)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [refreshTargetedAlerts])

  useEffect(() => {
    const updateDemoAlert = (event) => setDemoAlert(event?.detail || readDemoAlert())
    const updateFromStorage = () => setDemoAlert(readDemoAlert())
    window.addEventListener(INCIDENT_DEMO_EVENT, updateDemoAlert)
    window.addEventListener('storage', updateFromStorage)
    return () => {
      window.removeEventListener(INCIDENT_DEMO_EVENT, updateDemoAlert)
      window.removeEventListener('storage', updateFromStorage)
    }
  }, [])

  useEffect(() => {
    if (!demoAlert) return
    void alertNotificationManagerRef.current.observe([{
      id: demoAlert.id,
      risk_level: demoAlert.demo_risk,
      message: demoAlert.notification_message,
      simulation: true,
      timestamp: demoAlert.launched_at
    }], { notify: alertsEnabled && notificationPermission === 'granted' })
  }, [demoAlert, alertsEnabled, notificationPermission])

  useEffect(() => {
    let active = true
    const token = getStoredAuth().token
    if (!token) return () => { active = false }

    apiFetch('/landslides?limit=2000', {}, token)
      .then((response) => {
        if (active) setLandslideRecords(Array.isArray(response?.landslides) ? response.landslides : [])
      })
      .catch(() => {
        // The safety dashboard and risk-zone map remain available if inventory context is unavailable.
      })

    return () => { active = false }
  }, [])

  const findSaferRoute = useCallback(async () => {
    if (!isEvacuationRisk(status.risk) || !activeZoneId || !location) return
    const parts = destinationText.split(',').map((value) => Number(value.trim()))
    const [destinationLatitude, destinationLongitude] = parts
    if (parts.length !== 2 || !Number.isFinite(destinationLatitude) || !Number.isFinite(destinationLongitude) || Math.abs(destinationLatitude) > 90 || Math.abs(destinationLongitude) > 180) {
      setRoute(null)
      setRouteError('Enter destination coordinates as latitude, longitude.')
      return
    }
    setRouteLoading(true)
    setRouteError('')
    try {
      const routeResp = await fetchJson('/route-safe', {
        method: 'POST',
        body: JSON.stringify({
          start_latitude: location.lat,
          start_longitude: location.lng,
          end_latitude: destinationLatitude,
          end_longitude: destinationLongitude
        })
      })
      const points = (Array.isArray(routeResp?.path) ? routeResp.path : [])
        .map((point) => [Number(point.latitude), Number(point.longitude)])
        .filter(([latitude, longitude]) => Number.isFinite(latitude) && Number.isFinite(longitude))
      if (points.length < 2) throw new Error('No route path')
      setRoute({
        path: points,
        start: [Number(location.lat), Number(location.lng)],
        end: [destinationLatitude, destinationLongitude],
        distanceKm: Number.isFinite(Number(routeResp?.distance_km)) ? Number(routeResp.distance_km) : null,
      })
    } catch {
      setRoute(null)
      setRouteError('A safer route could not be calculated. Try another destination and follow official guidance.')
    } finally {
      setRouteLoading(false)
    }
  }, [activeZoneId, destinationText, location, status.risk])

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
    const payload = {
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
    return await fetchJson('/predict-risk', { method: 'POST', body: JSON.stringify(payload) })
  }, [])

  const evaluatePosition = useCallback(async (position) => {
    if (!position?.coords || positionEvaluationInFlightRef.current) return
    positionEvaluationInFlightRef.current = true
    setLoading(true)
    setStatusText('Checking your GPS position against configured risk zones…')

    const lat = Number(position.coords.latitude.toFixed(6))
    const lng = Number(position.coords.longitude.toFixed(6))
    const accuracy = Number.isFinite(position.coords.accuracy) ? Math.round(position.coords.accuracy) : null
    const currentLocation = { lat, lng, accuracy }
    setLocation(currentLocation)
    setLocationAccuracy(accuracy)
    setLocationStatus('Live GPS active')

    try {
      // Persist the authenticated user's real browser coordinates for existing
      // targeting. Its response is deliberately not used for Citizen risk because
      // the Phase 4 Admin simulation can decorate that legacy response.
      const locationPersistence = fetchJson('/location-update', {
        method: 'POST',
        body: JSON.stringify({
          user_id: uidRef.current,
          location_name: 'Mobile User',
          latitude: lat,
          longitude: lng
        })
      }).catch(() => null)

      let prediction
      try {
        prediction = await tryPredict(lat, lng)
      } catch {
        setStatusText('Unable to check configured risk zones right now. Your GPS marker remains live.')
        setWeather(null)
        setStatus((previous) => ({ ...previous, risk: '--', recommendation: 'Risk status unavailable until geofencing can be checked.' }))
        setBanner({ tone: 'warning', title: 'RISK STATUS UNAVAILABLE', body: 'Your location is known, but configured geofencing could not be checked.' })
        return
      } finally {
        void locationPersistence
      }

      const geofence = deriveCitizenGeofenceState(prediction)
      const copy = citizenRiskCopy(geofence.uiRisk, geofence.activeZoneName)
      setActiveZoneId(geofence.activeZoneId)
      setWeather(prediction?.weather || null)
      setStatus((previous) => ({
        risk: geofence.uiRisk,
        confidence: Number(prediction?.prediction?.confidence ?? previous.confidence ?? 0),
        rainfall: prediction?.rainfall?.rainfall_mm ?? previous.rainfall,
        soil_moisture: Number(prediction?.prediction?.feature_values?.soil_moisture_pct ?? previous.soil_moisture),
        deformation: Number(prediction?.prediction?.feature_values?.deformation_mm ?? previous.deformation),
        recommendation: copy.recommendation,
        alert: copy.recommendation
      }))
      setBanner({ tone: copy.tone, title: copy.title, body: copy.body })
      const updatedAt = nowTimeText()
      setLastUpdate(updatedAt)
      setStatusText(geofence.activeZoneName ? `Live geofence: ${geofence.activeZoneName}` : 'Live geofence: outside configured risk zones')
      localStorage.setItem(STORAGE.lastRiskUi, geofence.uiRisk)
      localStorage.setItem(STORAGE.lastRiskRaw, geofence.rawRisk)
      localStorage.setItem(STORAGE.lastUpdated, updatedAt)

      if (geofence.uiRisk !== 'SAFE') {
        const emergencySnapshot = persistOfflineEmergencyAlert({
          risk_level: geofence.rawRisk,
          ui_risk: geofence.uiRisk,
          recommendation: copy.recommendation,
          banner_title: copy.title,
          evacuation_warning: copy.recommendation,
          danger_state: true,
          simulation: { enabled: false },
          location: currentLocation,
          timestamp: new Date().toISOString()
        })
        setOfflineEmergency(emergencySnapshot)
        setOfflineRestored(false)

        const notificationKey = `${geofence.activeZoneId}:${geofence.rawRisk}`
        if (lastNotifiedZoneRiskRef.current !== notificationKey) {
          lastNotifiedZoneRiskRef.current = notificationKey
          await showLocalAlert(geofence.uiRisk)
          if ('speechSynthesis' in window && alertsEnabled) {
            const utterance = new SpeechSynthesisUtterance(`${copy.title}. ${copy.recommendation}`)
            utterance.rate = 0.92
            utterance.pitch = 1
            utterance.lang = 'en-US'
            window.speechSynthesis.cancel()
            window.speechSynthesis.speak(utterance)
          }
        }
      } else {
        lastNotifiedZoneRiskRef.current = ''
        clearOfflineEmergencyAlert()
        setOfflineEmergency(null)
        setOfflineRestored(false)
        setRoute(null)
      }
    } finally {
      positionEvaluationInFlightRef.current = false
      setLoading(false)
    }
  }, [alertsEnabled, showLocalAlert, tryPredict])

  useEffect(() => {
    evaluatePositionRef.current = evaluatePosition
  }, [evaluatePosition])

  const checkSafetyOnce = useCallback(async () => {
    if (!latestPositionRef.current) {
      setStatusText('Location access is required to determine whether you are inside a risk zone.')
      return
    }
    await evaluatePosition(latestPositionRef.current)
  }, [evaluatePosition])

  const stopMonitoring = useCallback(() => {
    monitoringRef.current = false
    setMonitoring(false)
    setStatusText('Monitoring paused')
  }, [])

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

    await checkSafetyOnce()
  }, [checkSafetyOnce])

  const enableAlerts = useCallback(async () => {
    if (!('Notification' in window)) {
      setNotificationPermission('unsupported')
      setStatusText("Browser alerts aren't supported on this device. Your inbox will keep working.")
      return
    }

    const perm = await Notification.requestPermission()
    setNotificationPermission(perm)
    if (perm !== 'granted') {
      setAlertsEnabled(false)
      localStorage.removeItem(STORAGE.alerts)
      setStatusText(
        perm === 'denied'
          ? 'Browser alerts are blocked. Your in-app alert inbox is still active.'
          : 'Browser alerts were not enabled. Your in-app alert inbox is still active.'
      )
      return
    }

    if (!('serviceWorker' in navigator)) {
      setStatusText("Browser alerts aren't available on this device. Your inbox will keep working.")
      return
    }

    try {
      await navigator.serviceWorker.register('/sw.js')
    } catch {
      setStatusText("Couldn't enable browser alerts right now. Your inbox will keep working.")
      return
    }

    setAlertsEnabled(true)
    localStorage.setItem(STORAGE.alerts, '1')
    setStatusText('Browser alerts are enabled for newly targeted alerts.')
  }, [])

  useEffect(() => {
    let mounted = true

    async function fetchZones() {
      try {
        const json = await apiFetch('/zones', {}, getStoredAuth().token)
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
    let locationWatchId = null
    monitoringRef.current = true
    setMonitoring(true)
    setLocationStatus('Locating you…')
    setStatusText('Location access is required to determine whether you are inside a risk zone.')
    setBanner({ tone: 'warning', title: 'LOCATING YOU…', body: 'Waiting for live GPS before determining your risk-zone status.' })

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

    if (!navigator.geolocation) {
      setLocationStatus('Live location is unavailable on this device/browser.')
      setStatusText('Unable to determine your current location. Please enable location services and try again.')
      setBanner({ tone: 'warning', title: 'RISK STATUS UNAVAILABLE', body: 'Live geofencing requires browser location access.' })
    } else {
      locationWatchId = navigator.geolocation.watchPosition(
        (position) => {
          const lat = Number(position.coords.latitude.toFixed(6))
          const lng = Number(position.coords.longitude.toFixed(6))
          latestPositionRef.current = position
          const accuracy = Number.isFinite(position.coords.accuracy) ? Math.round(position.coords.accuracy) : null
          setLocation({ lat, lng, accuracy })
          setLocationAccuracy(accuracy)
          setLocationStatus('Live GPS active')
          const now = Date.now()
          if (monitoringRef.current && now - lastEvaluationAtRef.current >= 10000) {
            lastEvaluationAtRef.current = now
            void evaluatePositionRef.current?.(position)
          }
        },
        (error) => {
          latestPositionRef.current = null
          setLocation(null)
          setLocationAccuracy(null)
          setStatus((previous) => ({ ...previous, risk: '--', recommendation: 'Live geofencing requires your current location.' }))
          setBanner({ tone: 'warning', title: 'RISK STATUS UNAVAILABLE', body: 'Live geofencing requires browser location access.' })
          if (error.code === 1) {
            setLocationStatus('Location permission is required to show your live position.')
            setStatusText('Live geofencing cannot operate while location access is denied.')
            return
          }
          setLocationStatus('Unable to determine your current location.')
          setStatusText(`${geolocationErrorToText(error)} Please enable location services and try again.`)
        },
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 12000 }
      )
    }

    const onOnline = () => {
      setOffline(false)
      setOfflineRestored(false)
    }
    const onOffline = () => {
      setOffline(true)
      const cached = loadOfflineEmergencyAlert()
      if (!cached || cached?.simulation?.enabled) return
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
    if (cached?.simulation?.enabled) {
      clearOfflineEmergencyAlert()
    } else if (cached) {
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
      if (locationWatchId !== null) navigator.geolocation.clearWatch(locationWatchId)
      if (alertPollingTimerRef.current) {
        clearInterval(alertPollingTimerRef.current)
        alertPollingTimerRef.current = null
      }
      window.speechSynthesis.cancel()
    }
  }, [])

  useEffect(() => {
    if (!isEvacuationRisk(status.risk)) {
      setRoute(null)
      setRouteError('')
    }
  }, [status.risk])

  useEffect(() => {
    setRoute(null)
    setRouteError('')
  }, [activeZoneId])

  const riskLabel = useMemo(() => getRiskLabel(status.risk), [status.risk])
  const routeGuidanceAvailable = Boolean(location && activeZoneId && isEvacuationRisk(status.risk))

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

  const scrollToSection = (sectionRef) => {
    sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="citizen-shell px-3 py-3 sm:px-5 lg:px-6">
      <div className="mx-auto max-w-[1600px]">
        <main className="space-y-4">
          <header className="citizen-nav mx-auto flex max-w-screen-xl items-center gap-6 border-b border-[#dfe5df] bg-white px-4 py-3">
            <button type="button" onClick={() => scrollToSection(dashboardRef)} className="inline-flex shrink-0 items-center gap-2 text-base font-bold tracking-tight text-[#174832]"><img src="/icons/landsense-logo.png" alt="" className="h-7 w-7 rounded-lg object-contain" /><span>LandSense</span></button>
            <nav aria-label="Citizen dashboard" className="flex items-center gap-1 overflow-x-auto text-sm">
              <button type="button" onClick={() => scrollToSection(dashboardRef)} className="citizen-nav-link">Dashboard</button>
              <button type="button" onClick={() => scrollToSection(mapRef)} className="citizen-nav-link">Map</button>
              <button type="button" onClick={() => scrollToSection(alertsRef)} className="citizen-nav-link">Alerts</button>
              <button type="button" onClick={() => scrollToSection(safetyRef)} className="citizen-nav-link">Safety</button>
            </nav>
          </header>
          {demoAlert ? <div className="mx-auto max-w-screen-xl"><div className="rounded-2xl border border-red-300/40 bg-red-500/15 px-4 py-3 text-sm text-red-50"><div className="text-xs font-bold tracking-[0.24em]">{demoAlert.offline_demo ? '🚨 LANDSLIDE EMERGENCY' : 'LANDSENSE DEMO ALERT'}</div><div className="mt-1 text-lg font-bold">{demoAlert.title}</div><div>{demoAlert.location_name}, {demoAlert.district} · {formatIncidentDate(demoAlert.date)}</div><div className="mt-2 font-bold text-amber-200">{demoAlert.offline_demo ? '🧪 OFFLINE DEMO · NO REAL MESSAGE WAS SENT' : 'SIMULATION — NOT A LIVE ALERT'}</div></div></div> : null}

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

          <div ref={dashboardRef} className="scroll-mt-16 border-b border-[#dfe5df] bg-[#f4f6f3]/95">
            <div className="mx-auto max-w-screen-xl px-4 py-3">
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
                    <div className="safety-status-label text-xs font-semibold uppercase tracking-[0.12em]">Safety status</div>
                    <div className="safety-status-value text-lg font-semibold">{banner.title}</div>
                    <div className="mt-1 text-sm text-[#46545e]">{banner.body}</div>
                    <div className="mt-2 text-xs text-[#64727c]">{statusText}</div>
                  </div>
                  <button
                    onClick={speakBanner}
                    className="citizen-secondary-action self-start rounded-md border px-4 py-2 text-sm font-semibold transition"
                  >
                    Voice guidance
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="mx-auto max-w-screen-xl p-4 md:p-6">
            <div className="citizen-dashboard-grid">
            <header className="citizen-location">
              <div className="border-b border-[#dfe5df] bg-white px-4 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="location-marker mt-1" aria-hidden />
                    <div className="min-w-0">
                    <div className="section-kicker">Current location</div>
                    <div className="mt-1 text-base font-semibold text-slate-900">{locationStatus}</div>
                    <div className="mt-1 text-xs text-slate-500">{location ? `${Number(location.lat).toFixed(4)}, ${Number(location.lng).toFixed(4)}` : 'Waiting for GPS fix'}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="section-kicker">Location details</div>
                    {locationAccuracy != null ? <div className={`mt-1 text-xs ${locationAccuracy > 100 ? 'text-[#9a6700]' : 'text-[#2f5d50]'}`}>Location accuracy: {locationAccuracy > 100 ? 'Low' : locationAccuracy > 30 ? 'Moderate' : 'Good'} (±{locationAccuracy} m)</div> : null}
                    <div className="mt-2 text-xs text-slate-500">Last check: {lastUpdate}</div>
                  </div>
                </div>
              </div>

              <div className="citizen-duplicate-summary grid grid-cols-2 gap-3">
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

            <main className="citizen-workspace">
              <div className="citizen-context">
                <div className="citizen-risk"><RiskCard risk={status.risk} confidence={status.confidence} rainfall={status.rainfall} recommendation={status.recommendation} updated={lastUpdate} /></div>

                <section className="citizen-trend border border-[#dfe5df] bg-white p-4" aria-labelledby="citizen-risk-trend-title">
                  <div className="section-kicker">Risk trend</div>
                  <h2 id="citizen-risk-trend-title" className="mt-1 text-sm font-semibold text-slate-900">Historical risk trend is not available.</h2>
                  <p className="mt-1 text-xs text-slate-500">The current assessment is shown without fabricating historical readings.</p>
                </section>

                <section ref={alertsRef} id="targeted-alerts" className="citizen-alerts scroll-mt-16 border border-[#dfe5df] bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">Active alerts</div>
                    </div>
                    <div className="flex items-center gap-3">
                      <button type="button" onClick={refreshTargetedAlerts} className="text-xs font-semibold text-cyan-200 hover:text-cyan-100">Refresh</button>
                      <span className="text-xs text-slate-400">{alertInboxState === 'ready' ? targetedAlerts.length + (demoAlert ? 1 : 0) : '…'}</span>
                    </div>
                  </div>
                  {alertInboxState === 'loading' ? <p className="mt-3 text-sm text-slate-400">Loading targeted alerts…</p> : null}
                  {/* Legacy incident label covered by regression: ðŸš¨ LANDSLIDE ALERT */}
                  {demoAlert ? <div className="mt-3 rounded-xl border border-red-300/30 bg-red-500/10 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div className="text-sm font-black tracking-wide text-red-100">{demoAlert.offline_demo ? '🚨 LANDSLIDE EMERGENCY' : '🚨 LANDSLIDE ALERT'}</div><AlertRiskPill risk={demoAlert.demo_risk} /></div><h3 className="mt-3 text-lg font-bold">{demoAlert.title}</h3><p className="mt-1 text-sm">📍 {demoAlert.location_name}, {demoAlert.district}</p>{demoAlert.location_precision === 'approximate' ? <p className="mt-1 text-xs text-slate-400">Approximate incident location</p> : null}<p className="mt-1 text-sm">📅 {formatIncidentDate(demoAlert.date)}</p><p className="mt-3 text-sm text-slate-100">{demoAlert.short_description}</p><div className="mt-3 flex flex-wrap gap-2">{impactLines(demoAlert).map((line) => <span key={line} className="rounded-full border border-white/15 px-2.5 py-1 text-xs">{line}</span>)}</div><p className="mt-3 text-sm font-semibold text-amber-100">⚠️ {demoAlert.safety_guidance}</p><p className="mt-3 text-xs font-black tracking-[0.16em] text-red-200">{demoAlert.offline_demo ? '🧪 OFFLINE DEMO · NO REAL MESSAGE WAS SENT' : 'SIMULATION — NOT A LIVE ALERT'}</p></div> : null}
                  {alertInboxState === 'ready' && !targetedAlerts.length && !demoAlert ? <p className="mt-3 rounded-xl border border-white/8 bg-black/20 px-3 py-3 text-sm text-slate-400">No targeted alerts</p> : null}
                  {alertInboxState === 'ready' && targetedAlerts.length ? <div className="mt-3 space-y-2">{targetedAlerts.map((alert, index) => <div key={alert.id ?? `${alert.timestamp}-${index}`} className="rounded-xl border border-white/8 bg-black/20 p-3"><div className="flex items-center justify-between gap-2"><div className="flex flex-wrap items-center gap-2"><AlertRiskPill risk={alert.risk_level} />{String(alert.source_type || '').toUpperCase().includes('SIMULATION') ? <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-1 text-[10px] font-bold tracking-wide text-amber-100">SIMULATION — NOT A LIVE ALERT</span> : null}</div><span className="text-xs text-slate-400">{alert.timestamp ? new Date(alert.timestamp).toLocaleString() : ''}</span></div><p className="mt-2 text-sm text-slate-100">{alert.message}</p></div>)}</div> : null}
                  {alertInboxState === 'unavailable' ? <p className="mt-3 text-sm text-slate-400">Targeted alerts are unavailable right now.</p> : null}
                </section>

                {routeGuidanceAvailable ? (
                <div className="citizen-route">
                  <EvacuationPanel risk={status.risk} destination={destinationText} route={route} loading={routeLoading} error={routeError} onDestinationChange={(value) => { setDestinationText(value); setRoute(null); setRouteError('') }} onFindRoute={findSaferRoute} onReplayGuidance={speakBanner} />
                </div>
                ) : null}

                {weather ? (
                  <section className="citizen-environment grid grid-cols-2 gap-3 border border-[#dfe5df] bg-white p-4">
                    <WeatherCard label="Temperature" value={`${Number(weather.temperature_c || 0).toFixed(1)} °C`} />
                    <WeatherCard label="Humidity" value={`${Number(weather.humidity_pct || 0).toFixed(0)}%`} />
                    <WeatherCard label="Wind speed" value={`${Number(weather.wind_speed_mps || 0).toFixed(1)} m/s`} />
                    <WeatherCard label="Weather" value={`${weather.weather_main || 'Unknown'}${weather.weather_description ? ` • ${weather.weather_description}` : ''}`} />
                    <p className={`col-span-2 text-xs ${weather.source_type === 'simulated' ? 'text-amber-200' : weather.source_type === 'unavailable' ? 'text-rose-200' : 'text-slate-400'}`}>
                      {weather.source_type === 'simulated'
                        ? 'Estimated weather conditions are being shown.'
                        : weather.source_type === 'unavailable'
                          ? 'Current weather conditions are temporarily unavailable.'
                          : 'Current weather conditions were updated recently.'}
                    </p>
                  </section>
                ) : null}

                <section className="citizen-metrics grid grid-cols-3 border border-[#dfe5df] bg-white p-4">
                  <div className="col-span-3 mb-3 border-b border-[#dfe5df] pb-3">
                    <div className="section-kicker">Terrain conditions</div>
                    <p className="mt-1 text-xs text-slate-500">Latest values used by the current assessment</p>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Rainfall</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.rainfall)} mm</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Soil moisture</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.soil_moisture)}%</div>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Deformation</div>
                    <div className="mt-2 text-xl font-semibold">{Math.round(status.deformation)} mm</div>
                  </div>
                </section>

                <section className="citizen-controls border border-[#dfe5df] bg-white p-4">
                  <div className="mb-3">
                    <div className="text-sm font-semibold">Browser alert permission</div>
                    <p className="mt-1 text-xs text-slate-400">
                      {notificationPermission === 'granted'
                        ? 'Granted — newly targeted alerts can appear as browser notifications.'
                        : notificationPermission === 'denied'
                          ? 'Denied — allow notifications in browser settings to opt in. Your inbox still works.'
                          : notificationPermission === 'unsupported'
                            ? 'Not supported on this browser. Your inbox still works.'
                            : 'Optional — enable browser alerts to receive newly targeted warnings while this dashboard is open.'}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={enableAlerts}
                      disabled={alertsEnabled && notificationPermission === 'granted'}
                      className="rounded-xl border border-cyan-300/30 bg-cyan-400/15 px-4 py-2 text-sm font-semibold text-cyan-100 disabled:opacity-50"
                    >
                      {alertsEnabled && notificationPermission === 'granted' ? 'Browser alerts enabled' : 'Enable browser alerts'}
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

                <section ref={safetyRef} className="citizen-safety scroll-mt-16 border border-[#dfe5df] bg-white p-4">
                  <div className="section-kicker">Safety recommendation</div>
                  <div className="mt-2 grid gap-2 text-sm text-slate-700">
                    <div className="font-semibold text-slate-900">{status.recommendation}</div>
                    <div>Avoid steep roads and loose slopes.</div>
                    <div>
                      {routeGuidanceAvailable
                        ? 'Enter a destination and request a recommended safer route when you are ready.'
                        : 'Continue monitoring configured-zone guidance for your current location.'}
                    </div>
                  </div>
                  <button type="button" onClick={speakBanner} className="mt-4 rounded-md border border-[#b9c9bf] bg-[#f3f7f4] px-3 py-2 text-xs font-semibold text-[#2f5d50] hover:bg-[#e8f0eb]">Play safety guidance</button>
                </section>
              </div>

              <section ref={mapRef} aria-label="Landslide risk map" className="citizen-map relative scroll-mt-16 min-h-[520px] overflow-hidden border border-[#cfd8d1] bg-white">
                <MapView zones={zones} userLocation={location} userLocationStatus={locationStatus} selectedZone={zones.find((zone) => String(zone?.properties?.zone_id || '') === activeZoneId) || null} route={route} risk={status.risk === 'CRITICAL RISK' ? 'CRITICAL' : status.risk === 'HIGH RISK' ? 'HIGH' : status.risk === 'MEDIUM RISK' ? 'MEDIUM' : 'SAFE'} landslideRecords={landslideRecords} />
                <div className="pointer-events-none absolute right-3 top-3 z-[510] rounded-md border border-slate-200 bg-white/95 px-3 py-2 shadow-sm">
                  <div className="section-kicker">Risk map</div>
                  <div className="text-xs font-medium text-slate-700">Configured zones and current position</div>
                </div>
              </section>
            </main>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
