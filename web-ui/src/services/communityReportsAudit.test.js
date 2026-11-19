import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('citizen empty state appears only after a successful reports response', async () => {
  const component = await readFile(new URL('../components/CommunityReports.jsx', import.meta.url), 'utf8')
  assert.match(component, /reportsLoadStatus === 'success' \? <p[^>]*>No reports submitted yet\.<\/p>/)
  assert.match(component, /reportsLoadStatus === 'error' \? <p role="alert"[^>]*>Your reports could not be loaded\.<\/p>/)
})

test('service worker passes API and auth requests through without respondWith', async () => {
  const worker = await readFile(new URL('../../public/sw.js', import.meta.url), 'utf8')
  assert.match(worker, /req\.method !== 'GET'/)
  assert.match(worker, /'\/auth'/)
  assert.match(worker, /'\/community-reports'/)
  assert.doesNotMatch(worker, /respondWith\(fetch\(req\)\)/)
  assert.match(worker, /catch \{/)
})
