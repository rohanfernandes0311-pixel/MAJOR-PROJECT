import test from 'node:test'
import assert from 'node:assert/strict'

globalThis.window = { location: { origin: 'https://landsense.test' } }
const { apiFetch } = await import('../auth/authClient.js')

test('authenticated Excel fetch returns binary instead of parsing JSON', async () => {
  const original = globalThis.fetch
  const workbook = new Blob(['workbook'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'https://landsense.test/admin/affected-zones/demo/httpsms-excel')
    assert.equal(options.headers.Authorization, 'Bearer admin-token')
    assert.equal(options.method, undefined)
    return { ok: true, blob: async () => workbook, json: () => assert.fail('must preserve Excel bytes') }
  }
  try {
    assert.equal(await apiFetch('/admin/affected-zones/demo/httpsms-excel', {}, 'admin-token', 'blob'), workbook)
  } finally { globalThis.fetch = original }
})

test('export errors preserve server details and status', async () => {
  const original = globalThis.fetch
  globalThis.fetch = async () => ({ ok: false, status: 422, text: async () => JSON.stringify({ detail: 'Please configure HTTPSMS_FROM_NUMBER.' }) })
  try {
    await assert.rejects(apiFetch('/export', {}, 'admin-token', 'blob'), (error) => error.status === 422 && error.message.includes('HTTPSMS_FROM_NUMBER'))
  } finally { globalThis.fetch = original }
})
