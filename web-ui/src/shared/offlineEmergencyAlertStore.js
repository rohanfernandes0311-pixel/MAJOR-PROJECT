const STORAGE_KEY = 'landsense_offline_emergency_alert_v1'

function safeParse(raw) {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function nowIso() {
  return new Date().toISOString()
}

export function loadOfflineEmergencyAlert() {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  const data = safeParse(raw)
  if (!data || typeof data !== 'object') return null
  if (!data.danger_state) return null
  return data
}

export function persistOfflineEmergencyAlert(payload) {
  const normalized = {
    status: 'active',
    saved_at: nowIso(),
    risk_level: String(payload?.risk_level || '--').toUpperCase(),
    ui_risk: String(payload?.ui_risk || '--').toUpperCase(),
    recommendation: String(payload?.recommendation || ''),
    banner_title: String(payload?.banner_title || 'Emergency warning active'),
    danger_state: Boolean(payload?.danger_state),
    evacuation_warning: String(payload?.evacuation_warning || payload?.recommendation || ''),
    simulation: payload?.simulation || { enabled: false, effective_risk: 'LOW', scenario_name: '' },
    timestamp: String(payload?.timestamp || nowIso()),
    location: payload?.location || null,
    source: 'browser-offline-store'
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}

export function clearOfflineEmergencyAlert() {
  localStorage.removeItem(STORAGE_KEY)
}

export function isDangerState(uiRisk, simulationEnabled) {
  const normalized = String(uiRisk || '--').toUpperCase()
  return normalized === 'HIGH RISK' || normalized === 'WARNING' || Boolean(simulationEnabled)
}
