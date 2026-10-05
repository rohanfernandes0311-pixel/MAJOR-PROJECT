import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transform } from 'esbuild'
import { createCitizenPrecipitationController, validPrecipitationObservation } from './citizenPrecipitation.js'

// Fixtures are test-only and never runtime fallbacks.
const epoch = Date.parse('2026-10-05T00:00:00Z')
const observation = { source: 'NASA GPM IMERG Early', unit: 'mm/h', precipitation_rate: 0.25,
  observed_at: '2026-10-04T20:00:00Z', interval_end: '2026-10-04T20:29:59Z', interval_minutes: 30,
  quality_index: 0.8, random_error_mm_h: 0.1, distance_km: 3, spatial_resolution_degrees: 0.1 }
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
function harness(request = async () => observation) {
  let time = epoch, sequence = 0
  const timers = new Map(), calls = [], states = []
  const controller = createCitizenPrecipitationController({ request: (...args) => { calls.push(args); return request(...args) },
    onChange: value => states.push(value), now: () => time,
    setTimer: (callback, delay) => { const id = ++sequence; timers.set(id, { callback, at: time+delay }); return id },
    clearTimer: id => timers.delete(id) })
  return { controller, calls, states, timers, state: () => states.at(-1),
    async advance(ms) {
      const end = time+ms
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a,b) => a[1].at-b[1].at)[0]
        if (!due) break
        time = due[1].at; timers.delete(due[0]); due[1].callback(); await flush()
      }
      time = end; await flush()
    } }
}

test('real observation accepted; invalid quality, values and timestamps rejected', () => {
  assert.equal(validPrecipitationObservation(observation, epoch), true)
  for (const change of [{ precipitation_rate: 134, source: 'synthetic' }, { quality_index: 0 },
    { precipitation_rate: null }, { precipitation_rate: NaN }, { precipitation_rate: -9999.9 },
    { quality_index: 2 }, { observed_at: 'bad' }, { observed_at: '2026-09-01' }, { unit: 'mm' },
    { interval_end: 'bad' }, { random_error_mm_h: -9999.9 }]) {
    assert.equal(validPrecipitationObservation({ ...observation, ...change }, epoch), false)
  }
})
test('GPS jitter and duplicate callbacks cause one request, with satellite refresh cadence', async () => {
  const h = harness()
  h.controller.setLocation({lat: 12, lng: 75}); await flush()
  for (let i=0; i<20; i++) h.controller.setLocation({lat:12.0001, lng:75})
  await flush(); assert.equal(h.calls.length, 1)
  assert.equal(h.state().observation.precipitation_rate, 0.25)
  await h.advance(900000); assert.equal(h.calls.length, 2)
})
test('stale response cannot overwrite newer location response', async () => {
  const resolves = [], h = harness(() => new Promise(resolve => resolves.push(resolve)))
  h.controller.setLocation({lat:12,lng:75}); await flush()
  h.controller.setLocation({lat:13,lng:75}); assert.equal(h.calls[0][2].aborted, true)
  await h.advance(60000)
  resolves[1]({...observation, precipitation_rate:20}); await flush()
  resolves[0](observation); await flush()
  assert.equal(h.state().observation.precipitation_rate, 20)
})
test('unavailable requests clear data without synthetic fallback', async () => {
  const h = harness(async () => { throw new Error('private upstream failure') })
  h.controller.setLocation({lat:12,lng:75}); await flush()
  assert.deepEqual(h.state(), {observation:null,loading:false})
})
test('location loss and disposal cancel timers and pending responses', async () => {
  let resolve; const h = harness(() => new Promise(done => {resolve=done}))
  h.controller.setLocation({lat:12,lng:75}); await flush()
  h.controller.setLocation(null); resolve(observation); await flush()
  assert.equal(h.state().observation,null); assert.equal(h.timers.size,0)
  h.controller.dispose(); h.controller.setLocation({lat:12,lng:75})
  await h.advance(900000); assert.equal(h.calls.length,1)
})
test('no request with missing or invalid coordinates', async () => {
  const h = harness()
  for (const location of [null, {}, {lat:91,lng:75}, {lat:12,lng:181}, {lat:NaN,lng:75}]) h.controller.setLocation(location)
  await flush(); assert.equal(h.calls.length,0)
})

test('verified zero accepted and rendered, while unavailable renders no numeric fallback', async () => {
  const zero = { ...observation, precipitation_rate: 0 }
  assert.equal(validPrecipitationObservation(zero, epoch), true)
  const source = await readFile(new URL('../shared/PrecipitationCard.jsx', import.meta.url), 'utf8')
  const { code } = await transform(source.replace("import React from 'react'", '').replace('export default function', 'return function'), { loader: 'jsx' })
  const Card = new Function('React', code)(React)
  const render = value => renderToStaticMarkup(React.createElement(Card, { observation: value }))
  const html = render(observation)
  for (const text of ['Recent precipitation', '0.25 mm/h', 'Latest available satellite observation', 'NASA GPM IMERG Early', 'Regional satellite estimate', 'Observed interval:', 'IST', '0.1°', '30-minute mean']) assert.ok(html.includes(text))
  assert.match(render(zero), /0\.00 mm\/h/)
  assert.match(render(null), /Live data unavailable\./)
  assert.doesNotMatch(render(null), /134|0\.00|mm\/h/)
})

test('IMERG state is confined to terrain card; prediction, SMAP, Weatherbit and single GPS remain', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.equal((source.match(/navigator\.geolocation\.watchPosition\(/g) || []).length, 1)
  assert.match(source, /precipitationControllerRef\.current\?\.setLocation\(location\)/)
  assert.match(source, /PrecipitationCard observation=\{precipitationObservation\}/)
  assert.doesNotMatch(source, /Math\.round\(status\.rainfall\)/)
  assert.match(source, /rainfall=\{status\.rainfall\}/)
  const prediction = source.split('const tryPredict =')[1].split('const evaluatePosition =')[0]
  assert.doesNotMatch(prediction, /precipitationObservation|IMERG/)
  assert.match(prediction, /soil_moisture_pct: 45\.0/)
  assert.match(source, /SoilMoistureCard observation=\{soilObservation\}/)
  assert.match(source, /weatherFields\(weather\)\.map/)
  assert.doesNotMatch(source, /EARTHDATA_TOKEN|VITE_EARTHDATA/)
})

test('terrain labels distinguish satellite observations from the unchanged deformation model input', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(source, /Regional satellite observations, separate from risk assessment/)
  const prediction = source.split('const tryPredict =')[1].split('const evaluatePosition =')[0]
  assert.match(prediction, /deformation_mm: 5\.0/)
  assert.match(prediction, /soil_moisture_pct: 45\.0/)
  assert.doesNotMatch(prediction, /soilObservation|precipitationObservation/)
  const markup = source.split('<SoilMoistureCard observation={soilObservation} loading={soilLoading} />')[1].split('</section>')[0]
  const { code } = await transform(`return (${markup})`, { loader: 'jsx' })
  const html = renderToStaticMarkup(new Function('React', 'status', code)(React, { deformation: 5 }))
  assert.match(html, /Deformation/)
  assert.match(html, /5 mm/)
  assert.match(html, /Current model input/)
  assert.match(html, /Not a live satellite measurement/)
  assert.doesNotMatch(html, /NASA|Sentinel|NISAR|InSAR/)
})

test('valid data clears when refresh fails and cannot reappear as synthetic rainfall', async () => {
  let fail = false
  const h = harness(async () => { if (fail) throw new Error('upstream'); return observation })
  h.controller.setLocation({ lat: 12, lng: 75 }); await flush()
  assert.equal(h.state().observation.precipitation_rate, 0.25)
  fail = true; await h.advance(900000)
  assert.deepEqual(h.state(), { observation: null, loading: false })
})

test('crossing a native grid boundary clears previous cell immediately and remains throttled', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 12.099, lng: 75.05 }); await flush()
  h.controller.setLocation({ lat: 12.101, lng: 75.05 }); await flush()
  assert.equal(h.state().observation, null)
  assert.equal(h.calls.length, 1)
  await h.advance(60000)
  assert.equal(h.calls.length, 2)
  assert.equal(h.calls[1][0], 12.101)
})
