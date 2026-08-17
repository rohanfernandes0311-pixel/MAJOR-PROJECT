const RISK_ORDER = { LOW: 0, SAFE: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 }

function normalizeRisk(value) {
  return String(value || '').trim().toUpperCase()
}

function toCitizenUiRisk(value) {
  const risk = normalizeRisk(value)
  if (risk === 'MEDIUM') return 'MEDIUM RISK'
  if (risk === 'HIGH') return 'HIGH RISK'
  if (risk === 'CRITICAL') return 'CRITICAL RISK'
  return 'SAFE'
}

function deriveCitizenGeofenceState(response) {
  const matches = Array.isArray(response?.zone_matches) ? response.zone_matches : []
  const containingMatches = matches.filter((match) => match?.contains !== false)
  if (!containingMatches.length) {
    return { rawRisk: 'SAFE', uiRisk: 'SAFE', activeZoneId: '', activeZoneName: '', matches: [] }
  }

  const highestMatch = containingMatches.reduce((current, match) => {
    const currentRisk = normalizeRisk(current?.risk_level)
    const matchRisk = normalizeRisk(match?.risk_level)
    return (RISK_ORDER[matchRisk] ?? 0) > (RISK_ORDER[currentRisk] ?? 0) ? match : current
  }, containingMatches[0])
  const rawRisk = normalizeRisk(highestMatch?.risk_level || response?.zone_risk)

  return {
    rawRisk: RISK_ORDER[rawRisk] > 0 ? rawRisk : 'SAFE',
    uiRisk: toCitizenUiRisk(rawRisk),
    activeZoneId: String(highestMatch?.zone_id || ''),
    activeZoneName: String(highestMatch?.name || highestMatch?.zone_name || ''),
    matches: containingMatches
  }
}

function citizenRiskCopy(uiRisk, zoneName = '') {
  const area = zoneName ? ` You are inside ${zoneName}.` : ''
  if (uiRisk === 'CRITICAL RISK') return {
    tone: 'danger',
    title: 'CRITICAL LANDSLIDE RISK',
    recommendation: 'Follow official emergency guidance immediately. Move to a safe location if instructed.',
    body: `Your current location is inside a CRITICAL risk zone.${area}`
  }
  if (uiRisk === 'HIGH RISK') return {
    tone: 'danger',
    title: 'HIGH LANDSLIDE RISK',
    recommendation: 'Follow local safety guidance and prepare to move to a safer location if instructed.',
    body: `Your current location is inside a HIGH-risk zone.${area}`
  }
  if (uiRisk === 'MEDIUM RISK') return {
    tone: 'warning',
    title: 'MEDIUM RISK',
    recommendation: 'Stay alert and monitor official guidance.',
    body: `You are currently inside a monitored landslide-risk area.${area}`
  }
  return {
    tone: 'safe',
    title: 'SAFE',
    recommendation: 'Continue monitoring local safety guidance.',
    body: 'You are currently outside configured risk zones.'
  }
}

export { citizenRiskCopy, deriveCitizenGeofenceState, normalizeRisk, toCitizenUiRisk }
