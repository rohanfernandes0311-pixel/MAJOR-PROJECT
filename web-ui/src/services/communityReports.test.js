import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = (path) => readFile(new URL(path, import.meta.url), 'utf8')

test('citizen reporting uses authenticated endpoints and only the citizen report schema', async () => {
  const source = await readSource('../components/CommunityReports.jsx')
  assert.match(source, /apiFetch\('\/community-reports'/)
  assert.match(source, /\/community-reports\/mine\?limit=20/)
  assert.match(source, /No photograph is collected/)
  assert.match(source, /Reports are community observations\. They do not change official risk scores or hazard zones/)
  assert.doesNotMatch(source, /FormData|URL\.createObjectURL/)
})

test('community markers use a distinct Leaflet layer and status styling, separate from zones', async () => {
  const map = await readSource('../shared/MapView.jsx')
  assert.match(map, /const communityReportLayer = L\.layerGroup\(\)\.addTo\(map\)/)
  assert.match(map, /Community reports · separate from official zones/)
  assert.match(map, /showRejectedCommunityReports/)
  assert.match(map, /Community reports · separate from official zones/)
})

test('admin reports are loaded and reviewed through protected admin API routes', async () => {
  const source = await readSource('../components/CommunityReports.jsx')
  assert.match(source, /\/admin\/community-reports\?\$\{params\}/)
  assert.match(source, /\/admin\/community-reports\/\$\{encodeURIComponent\(selected\.report\.id\)\}\/review/)
  assert.match(source, /Status history/)
  assert.match(source, /Mark Under Review/)
  assert.match(source, /Verify/)
  assert.match(source, /Reject/)
})
