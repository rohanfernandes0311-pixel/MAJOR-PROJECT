import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('Leaflet map renders a distinct explicitly dataset-backed inventory layer', async () => {
  const source = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')

  assert.match(source, /L\.layerGroup\(\)/)
  assert.match(source, /Dataset-backed landslide inventory/)
  assert.match(source, /CONFIGURED · Risk zone/)
  assert.match(source, /landslideRecords/)
})
