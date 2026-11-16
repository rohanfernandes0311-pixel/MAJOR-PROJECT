import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { buildAdminIntelligence } from './adminIntelligence.js'

const response = {
  zone: { zone_id: 'WYD-03', name: 'Wayanad Critical Scar', configured_risk: 'HIGH' },
  weatherSource: 'REAL',
  historicalContext: { status: 'AVAILABLE', nearby_count: 12 },
  recentIncidentStatus: 'VERIFIED · DEMO SCENARIO',
  mlRisk: { status: 'AVAILABLE', risk: 'HIGH' },
  assessment: {
    overallRisk: 'HIGH', mlRisk: 'HIGH', confidence: null, confidenceLabel: 'NOT_AVAILABLE',
    dataQuality: 'GOOD', recommendedAction: 'PREVIEW_TARGETED_ALERT', automaticAlert: false,
    explanations: ['The existing ML model predicts HIGH.'],
    factors: [{ factor: 'ml_prediction', status: 'HIGH', impact: 'ELEVATED', available: true, explanation: 'The existing ML model predicts HIGH.' }],
  },
}

test('frontend presents the backend assessment without recalculating it', () => {
  const result = buildAdminIntelligence(response)
  assert.equal(result.overallRisk, 'HIGH')
  assert.equal(result.confidenceLabel, 'NOT_AVAILABLE')
  assert.equal(result.dataQuality, 'GOOD')
  assert.equal(result.recommendedAction, 'PREVIEW_TARGETED_ALERT')
  assert.deepEqual(result.factors, response.assessment.factors)
  assert.equal(result.automaticAlert, false)
})

test('invalid or incomplete endpoint responses fail closed', () => {
  assert.equal(buildAdminIntelligence(null), null)
  assert.equal(buildAdminIntelligence({ zone: {} }), null)
})

test('Admin renders risk, explanations, sources, quality, recommendation, and alert safety from the assessment', async () => {
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /assessment\.overallRisk/)
  assert.match(source, /factor\.explanation/)
  assert.match(source, /Assessment weather source/)
  assert.match(source, /assessment\.dataQuality/)
  assert.match(source, /assessment\.recommendedAction/)
  assert.match(source, /assessment\.automaticAlert === false \? 'OFF'/)
  assert.doesNotMatch(source, /automaticAlert.*apiFetch/)
})

test('Citizen UI remains free of Admin intelligence details', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  for (const adminOnly of ['LANDSLIDE INTELLIGENCE', 'Historical landslides inside zone', 'PREVIEW_TARGETED_ALERT', 'confidenceLabel']) {
    assert.doesNotMatch(source, new RegExp(adminOnly))
  }
})
