import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transform } from 'esbuild'
import { createCitizenEnvironmentController, validSoilObservation } from './citizenEnvironment.js'

// Fixtures are test-only and never runtime fallbacks.
const epoch = Date.parse('2026-10-05T00:00:00Z')
const observation = { source: 'NASA SMAP NRT', unit: '% water by volume', soil_moisture_percent: 17.257299,
  observed_at: '2026-10-04T00:51:13Z', retrieval_qual_flag: 8, surface_flag: 128,
  distance_km: 32.8, spatial_resolution_km: 36 }
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
function harness(request = async () => observation) {
  let time = epoch, sequence = 0
  const timers = new Map(), calls = [], states = []
  const controller = createCitizenEnvironmentController({ request: (...args) => { calls.push(args); return request(...args) },
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
  assert.equal(validSoilObservation(observation, epoch), true)
  for (const change of [{ soil_moisture_percent: 45, source: 'synthetic' }, { retrieval_qual_flag: 9 },
    { soil_moisture_percent: null }, { soil_moisture_percent: NaN }, { soil_moisture_percent: 0 },
    { surface_flag: 136 }, { observed_at: 'bad' }, { observed_at: '2026-09-01' }]) {
    assert.equal(validSoilObservation({ ...observation, ...change }, epoch), false)
  }
})
test('GPS jitter and duplicate callbacks cause one request, with satellite refresh cadence', async () => {
  const h = harness()
  h.controller.setLocation({lat: 12, lng: 75}); await flush()
  for (let i=0; i<20; i++) h.controller.setLocation({lat:12.0001, lng:75})
  await flush(); assert.equal(h.calls.length, 1)
  assert.equal(h.state().observation.soil_moisture_percent, 17.257299)
  await h.advance(1800000); assert.equal(h.calls.length, 2)
})
test('stale response cannot overwrite newer location response', async () => {
  const resolves = [], h = harness(() => new Promise(resolve => resolves.push(resolve)))
  h.controller.setLocation({lat:12,lng:75}); await flush()
  h.controller.setLocation({lat:13,lng:75}); assert.equal(h.calls[0][2].aborted, true)
  await h.advance(60000)
  resolves[1]({...observation, soil_moisture_percent:20}); await flush()
  resolves[0](observation); await flush()
  assert.equal(h.state().observation.soil_moisture_percent, 20)
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
  await h.advance(1800000); assert.equal(h.calls.length,1)
})
test('no request with missing or invalid coordinates', async () => {
  const h = harness()
  for (const location of [null, {}, {lat:91,lng:75}, {lat:12,lng:181}, {lat:NaN,lng:75}]) h.controller.setLocation(location)
  await flush(); assert.equal(h.calls.length,0)
})
test('card renders percentage, source, regional metadata and unavailable state', async () => {
  const source = await readFile(new URL('../shared/SoilMoistureCard.jsx', import.meta.url),'utf8')
  const {code} = await transform(source.replace("import React from 'react'", '').replace('export default function', 'return function'), {loader:'jsx'})
  const Card = new Function('React', code)(React)
  const html = renderToStaticMarkup(React.createElement(Card,{observation}))
  assert.match(html,/17\.26%/); assert.match(html,/Water by volume/); assert.match(html,/NASA SMAP NRT/)
  assert.match(html,/Latest available satellite observation/)
  assert.match(html,/Regional satellite estimate/); assert.match(html,/32\.8 km/); assert.match(html,/36 km/); assert.match(html,/IST/)
  const unavailable = renderToStaticMarkup(React.createElement(Card,{observation:null}))
  assert.match(unavailable,/Live data unavailable\./); assert.doesNotMatch(unavailable,/45%|0%/)
})
test('display state isolated from prediction; existing GPS, map and Weatherbit retained', async () => {
  const source = await readFile(new URL('../pages/Public.jsx',import.meta.url),'utf8')
  assert.equal((source.match(/navigator\.geolocation\.watchPosition\(/g)||[]).length,1)
  assert.match(source,/environmentControllerRef\.current\?\.setLocation\(location\)/)
  assert.match(source,/SoilMoistureCard observation=\{soilObservation\}/)
  assert.doesNotMatch(source,/Math\.round\(status\.soil_moisture\)/)
  const prediction = source.split('const tryPredict =')[1].split('const evaluatePosition =')[0]
  assert.match(prediction,/soil_moisture_pct: 45\.0/); assert.doesNotMatch(prediction,/soilObservation|SMAP/)
  assert.match(source,/weatherFields\(weather\)\.map/); assert.match(source,/userLocation=\{location\}/)
  assert.doesNotMatch(source,/EARTHDATA_TOKEN|VITE_EARTHDATA/)
  const proxy = await readFile(new URL('../../vite.config.js',import.meta.url),'utf8')
  assert.match(proxy,/'\/citizen\/environment'/)
})
