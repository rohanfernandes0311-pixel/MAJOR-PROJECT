import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('service worker never caches JWT-scoped alert responses', async () => {
  const source = await readFile(new URL('../../public/sw.js', import.meta.url), 'utf8')

  assert.match(source, /url\.pathname\.startsWith\('\/alerts\/'\)/)
  assert.match(source, /req\.headers\.has\('Authorization'\)/)
  assert.match(source, /event\.respondWith\(fetch\(req\)\)/)
})
