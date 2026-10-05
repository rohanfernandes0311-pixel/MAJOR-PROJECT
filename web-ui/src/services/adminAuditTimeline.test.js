import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const timelineUrl = new URL('../components/AdminAuditTimeline.jsx', import.meta.url)
const adminUrl = new URL('../pages/Admin.jsx', import.meta.url)
const viteConfigUrl = new URL('../../vite.config.js', import.meta.url)

test('Admin timeline renders newest-first historical events and controlled categories', async () => {
  const source = await readFile(timelineUrl, 'utf8')
  assert.match(source, /ADMIN AUDIT/)
  assert.match(source, /Event timeline/)
  assert.match(source, /Newest first/)
  assert.match(source, /new Date\(b\.timestampUtc\).*new Date\(a\.timestampUtc\)/s)
  for (const category of ['ALL', 'INTELLIGENCE', 'ADMIN_ACTION', 'INCIDENT', 'ALERT', 'SIMULATION']) assert.match(source, new RegExp(category))
})

test('timeline distinguishes real, simulation, preview, activation, risk, and expandable details', async () => {
  const source = await readFile(timelineUrl, 'utf8')
  assert.match(source, /event\.mode === 'REAL'/)
  assert.match(source, /event\.risk/)
  assert.match(source, /event\.eventType/)
  assert.match(source, /<details/)
  assert.match(source, /Event details/)
  assert.match(source, /recipientCount: 'Recipients'/)
  assert.match(source, /externalNotificationsSuppressed/)
})

test('timeline provides loading, empty, error, retry, and bounded load-more states', async () => {
  const source = await readFile(timelineUrl, 'utf8')
  assert.match(source, /Loading audit events\.\.\./)
  assert.match(source, /No audit events yet\./)
  assert.match(source, /No audit events are available for this filter\./)
  assert.match(source, /Audit timeline unavailable\./)
  assert.match(source, /onClick=\{onRetry\}/)
  assert.match(source, /Load more events/)
  assert.match(source, /onClick=\{onLoadMore\}/)
})

test('development proxy sends the complete Admin API namespace to FastAPI', async () => {
  const source = await readFile(viteConfigUrl, 'utf8')
  assert.match(source, /'\/admin'/)
  assert.doesNotMatch(source, /'\/admin\/simulation'/)
})

test('Admin loads a bounded timeline and records only meaningful UI operations', async () => {
  const source = await readFile(adminUrl, 'utf8')
  assert.match(source, /\/admin\/audit\/events\?limit=50&offset=/)
  assert.match(source, /event_type: 'ZONE_SELECTED'/)
  assert.match(source, /event_type: 'INCIDENT_SELECTED'/)
  assert.match(source, /event_type: 'DEMO_INCIDENT_LAUNCHED'/)
  assert.match(source, /event_type: 'DEMO_ALERT_GENERATED'/)
  assert.doesNotMatch(source, /watchPosition[\s\S]*recordUiAuditEvent/)
})

test('backend operations, not the UI timeline, own preview and activation records', async () => {
  const [timeline, admin] = await Promise.all([readFile(timelineUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(admin, /apiFetch\('\/admin\/affected-zones\/preview'/)
  assert.match(admin, /apiFetch\('\/admin\/affected-zones\/activate'/)
  assert.doesNotMatch(admin, /recordUiAuditEvent\(\{ event_type: 'ALERT_ACTIVATED'/)
  assert.doesNotMatch(timeline, /apiFetch|affected-zones\/activate/)
})

test('timeline renders only a safe metadata allowlist while removed decision support stays absent', async () => {
  const [timeline, admin] = await Promise.all([readFile(timelineUrl, 'utf8'), readFile(adminUrl, 'utf8')])
  assert.match(timeline, /DETAIL_LABELS/)
  assert.doesNotMatch(timeline, /phone_number|phone_masked|otp|JWT|firebase|latitude|longitude/i)
  assert.match(timeline, /current Decision Support panel remains authoritative/)
  assert.doesNotMatch(admin, /AdminDecisionSupport|ADMIN DECISION SUPPORT|No configured zone selected/)
  assert.doesNotMatch(admin, /<div className="mt-4"><AdminDecisionSupport/)
  assert.match(admin, /<AdminAuditTimeline/)
})

test('Citizen UI contains no Admin audit timeline', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /AdminAuditTimeline|ADMIN AUDIT|RECIPIENT PREVIEW OPENED|ALERT ACTIVATED/)
})
