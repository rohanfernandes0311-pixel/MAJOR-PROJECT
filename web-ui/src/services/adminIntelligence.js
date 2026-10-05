const VALID_SOURCE_STATES = new Set(['REAL', 'SIMULATED', 'UNAVAILABLE'])

export function buildAdminIntelligence(base) {
  if (!base?.zone || !base?.assessment) return null
  const weatherSource = VALID_SOURCE_STATES.has(String(base.weatherSource).toUpperCase())
    ? String(base.weatherSource).toUpperCase()
    : 'UNAVAILABLE'
  return {
    ...base,
    weatherSource,
    overallRisk: base.assessment.overallRisk,
    confidence: base.assessment.confidence,
    confidenceLabel: base.assessment.confidenceLabel,
    factors: Array.isArray(base.assessment.factors) ? base.assessment.factors : [],
    explanations: Array.isArray(base.assessment.explanations) ? base.assessment.explanations : [],
    dataQuality: base.assessment.dataQuality,
    recommendedAction: base.assessment.recommendedAction,
    automaticAlert: base.assessment.automaticAlert,
  }
}
