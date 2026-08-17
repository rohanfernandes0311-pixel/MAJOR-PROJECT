import test from 'node:test'
import assert from 'node:assert/strict'
import { citizenRiskCopy, deriveCitizenGeofenceState } from './citizenGeofence.js'

test('outside every configured zone is SAFE even when model final risk is high', () => {
  const state = deriveCitizenGeofenceState({ zone_matches: [], zone_risk: 'LOW', final_risk: 'HIGH' })
  assert.equal(state.uiRisk, 'SAFE')
  assert.match(citizenRiskCopy(state.uiRisk).body, /outside configured risk zones/)
})

for (const [rawRisk, uiRisk] of [['MEDIUM', 'MEDIUM RISK'], ['HIGH', 'HIGH RISK'], ['CRITICAL', 'CRITICAL RISK']]) {
  test(`configured ${rawRisk} containment produces ${uiRisk}`, () => {
    const state = deriveCitizenGeofenceState({
      zone_matches: [{ zone_id: `${rawRisk}-1`, name: `${rawRisk} zone`, risk_level: rawRisk }],
      zone_risk: rawRisk,
      simulation: { enabled: true, effective_risk: 'CRITICAL' }
    })
    assert.equal(state.uiRisk, uiRisk)
    assert.equal(state.activeZoneId, `${rawRisk}-1`)
  })
}

test('highest containing configured zone wins without consulting simulation fields', () => {
  const state = deriveCitizenGeofenceState({
    zone_matches: [
      { zone_id: 'medium', name: 'Medium', risk_level: 'MEDIUM' },
      { zone_id: 'critical', name: 'Critical', risk_level: 'CRITICAL' }
    ],
    simulation: { enabled: true, effective_risk: 'LOW' }
  })
  assert.equal(state.rawRisk, 'CRITICAL')
  assert.equal(state.activeZoneId, 'critical')
})
