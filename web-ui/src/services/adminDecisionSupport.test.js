import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const panelUrl = new URL('../components/AdminDecisionSupport.jsx', import.meta.url)
const adminUrl = new URL('../pages/Admin.jsx', import.meta.url)

test('decision panel renders authoritative risk, evidence, confidence, quality, population, and recommendation', async () => {
  const source = await readFile(panelUrl, 'utf8')
  assert.match(source, /ADMIN DECISION SUPPORT/)
  assert.match(source, /assessment\?\.overallRisk/)
  assert.match(source, /assessment\?\.recommendedAction/)
  assert.match(source, /assessment\?\.confidence/)
  assert.match(source, /assessment\?\.dataQuality/)
  assert.match(source, /factor\.explanation/)
  assert.match(source, /affected\?\.insideUsers/)
  assert.match(source, /affected\?\.outsideUsers/)
  assert.match(source, /affected\?\.recipientCount/)
  assert.match(source, /affected\?\.smsEligibleCount/)
  assert.doesNotMatch(source, /calculateRisk|combineRisk|riskScore/i)
})

test('decision states are readable and fail closed without stale intelligence', async () => {
  const [panel, admin] = await Promise.all([readFile(panelUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(panel, /Select a configured zone first\./)
  assert.match(panel, /Loading intelligence\.\.\./)
  assert.match(panel, /Decision support unavailable\./)
  assert.match(panel, /Affected population unavailable\./)
  assert.match(panel, /Data quality: PARTIAL/)
  assert.match(panel, /Data quality: LIMITED/)
  assert.match(panel, /Data quality: UNAVAILABLE/)
  assert.match(admin, /setIntelligenceLoading\(true\)[\s\S]*setZoneIntelligence\(null\)[\s\S]*apiFetch\(`\/admin\/intelligence\/zones/)
})

test('real and simulated decision populations remain separated and simulation disables real activation', async () => {
  const source = await readFile(panelUrl, 'utf8')
  assert.match(source, /SIMULATION MODE ACTIVE/)
  assert.match(source, /Real alert activation is disabled\./)
  assert.match(source, />REAL</)
  assert.match(source, />SIMULATION</)
  assert.match(source, /demo participants/)
  assert.doesNotMatch(source, /affected.*\+.*simulated|recipientCount.*\+.*simulated/s)
})

test('primary action reuses Phase 5 preview with authoritative assessment risk and never activates', async () => {
  const [panel, admin] = await Promise.all([readFile(panelUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(panel, /Preview Targeted Alert/)
  assert.match(panel, /onClick=\{onPreview\}/)
  assert.match(panel, /data-zone-id=\{selectedZoneId \|\| ''\}/)
  assert.match(panel, /data-risk=\{assessment\?\.overallRisk \|\| ''\}/)
  assert.match(panel, /Automatic alert:/)
  assert.match(admin, /previewDecisionRecipients/)
  assert.match(admin, /previewRecipients\(zoneIntelligence\?\.assessment\?\.overallRisk\)/)
  assert.match(admin, /apiFetch\('\/admin\/affected-zones\/preview'/)
  assert.doesNotMatch(panel, /affected-zones\/activate|send_sms|Firebase|Twilio/)
})

test('incident context and map anchor retain configured-zone intelligence without the removed panel', async () => {
  const [panel, admin] = await Promise.all([readFile(panelUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(panel, /intelligence\.recentIncident/)
  assert.match(panel, /Location precision:/)
  assert.match(panel, /Recent incident: None identified/)
  assert.match(panel, /href="#incident-intelligence-map"/)
  assert.match(admin, /id="incident-intelligence-map"/)
  assert.match(admin, /intelligence=\{zoneIntelligence\}/)
  assert.doesNotMatch(admin, /AdminDecisionSupport|ADMIN DECISION SUPPORT|No configured zone selected/)
  assert.doesNotMatch(admin, /<div className="mt-4"><AdminDecisionSupport/)
})

test('Citizen remains unchanged by Admin decision support', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /ADMIN DECISION SUPPORT|Decision support unavailable|ADMIN REVIEW REQUIRED/)
})
