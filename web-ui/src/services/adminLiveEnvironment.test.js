import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transform } from 'esbuild'
import { buildAdminIntelligence, createAdminLiveEnvironmentController } from './adminIntelligence.js'
import { weatherFields } from './citizenWeather.js'

// Test-only observations; never runtime defaults.
const epoch = Date.parse('2026-10-06T06:00:00Z')
const weather = { source: 'weatherbit', temperature_c: 23, humidity_pct: 88, wind_speed_mps: 0, observed_at: '2026-10-06T05:00:00Z' }
const precipitation = { source: 'NASA GPM IMERG Early', precipitation_rate: 0.31, unit: 'mm/h',
  observed_at: '2026-10-06T02:00:00Z', interval_end: '2026-10-06T02:30:00Z', interval_minutes: 30,
  quality_index: 0.8, random_error_mm_h: 0.1, distance_km: 3, spatial_resolution_degrees: 0.1 }
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve() }

function harness(request = async path => path.includes('/weather/') ? weather : precipitation) {
  let time = epoch, sequence = 0
  const timers = new Map(), calls = [], states = []
  const controller = createAdminLiveEnvironmentController({
    request: (path, options) => { calls.push({ path, options }); return request(path, options) },
    onChange: value => states.push(value), now: () => time,
    setTimer: (callback, delay) => { const id = ++sequence; timers.set(id, { callback, at: time + delay }); return id },
    clearTimer: id => timers.delete(id),
  })
  return { controller, calls, timers, state: () => states.at(-1),
    async advance(ms) {
      const end = time + ms
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
        if (!due) break
        time = due[1].at; timers.delete(due[0]); due[1].callback(); await flush()
      }
      time = end; await flush()
    },
  }
}

let renderSignals
async function render(environment) {
  if (!renderSignals) {
    const admin = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
    const card = await readFile(new URL('../shared/PrecipitationCard.jsx', import.meta.url), 'utf8')
    const { code: cardCode } = await transform(card.replace("import React from 'react'", '').replace('export default function', 'return function'), { loader: 'jsx' })
    const PrecipitationCard = new Function('React', cardCode)(React)
    const component = admin.slice(admin.indexOf('export function AdminEnvironmentalSignals'), admin.indexOf('\nfunction IntelligenceCard'))
    const { code } = await transform(component.replace('export function', 'return function'), { loader: 'jsx' })
    renderSignals = new Function('React', 'weatherFields', 'PrecipitationCard', code)(React, weatherFields, PrecipitationCard)
  }
  return renderToStaticMarkup(React.createElement(renderSignals, { environment }))
}

test('all configured zones request exactly the intelligence response coordinates', async () => {
  const geojson = JSON.parse(await readFile(new URL('../../../config/risk_zones.geojson', import.meta.url), 'utf8'))
  const zones = [
    { zone_id: 'RGD-01', latitude: 18.405, longitude: 73.285 },
    { zone_id: 'IDK-02', latitude: 9.85, longitude: 76.91 },
    { zone_id: 'WYD-03', latitude: 11.594999999999999, longitude: 76.12 },
  ]
  assert.deepEqual(zones.map(z => z.zone_id), geojson.features.map(f => f.properties.zone_id))
  const h = harness()
  for (const zone of zones) {
    h.controller.setZone(zone); await h.advance(60000)
    for (const call of h.calls.slice(-2)) {
      const url = new URL(call.path, 'https://fixture.local')
      assert.equal(url.searchParams.get('latitude'), String(zone.latitude))
      assert.equal(url.searchParams.get('longitude'), String(zone.longitude))
      assert.equal(call.options.cache, 'no-store')
    }
    assert.equal(h.state().zoneId, zone.zone_id)
  }
  assert.equal(h.calls.length, 6)
  assert.deepEqual(h.calls.map(c => new URL(c.path, 'https://fixture.local').pathname), Array(3).fill(['/citizen/weather/current', '/citizen/environment/precipitation']).flat())
})

test('response coordinates, including zero, are passed through without centroid or GPS calculation', async () => {
  const h = harness()
  h.controller.setZone({ zone_id: 'response-only', latitude: 0, longitude: 0 }); await flush()
  assert.ok(h.calls.every(c => c.path.endsWith('?latitude=0&longitude=0')))
  for (const zone of [null, { zone_id: 'bad' }, { zone_id: 'bad', latitude: '12', longitude: 75 }, { zone_id: 'bad', latitude: 91, longitude: 75 }]) {
    h.controller.setZone(zone); await flush()
    assert.equal(h.state().weather, null)
    assert.equal(h.state().weatherLoading, false)
  }
  assert.equal(h.calls.length, 2)
})

test('Weatherbit measurements and IMERG native rates render with actual provenance and verified zeros', async () => {
  const h = harness(); h.controller.setZone({ zone_id: 'test', latitude: 12, longitude: 75 }); await flush()
  const html = await render(h.state())
  for (const text of ['23.0 °C', '88 %', '0.0 m/s', '0.31 mm/h', 'Weatherbit', 'NASA GPM IMERG Early', 'Observed:', 'Observed interval:', 'LIVE', 'separate from risk assessment']) assert.ok(html.includes(text), text)
  assert.match(await render({ ...h.state(), precipitation: { ...precipitation, precipitation_rate: 0 } }), /0\.00 mm\/h/)
})

test('missing weather fields stay unavailable while the remaining measurement is live', async () => {
  const html = await render({ weather: { source: 'weatherbit', temperature_c: 0, humidity_pct: null, wind_speed_mps: null }, precipitation: null })
  assert.match(html, /0\.0 °C/)
  assert.equal((html.match(/>Unavailable</g) || []).length, 2)
  assert.doesNotMatch(html, /0\.0 m\/s|0 %|Observed:/)
})

test('independent service failures clear measurements without synthetic or zero fallbacks', async () => {
  for (const failure of ['weather', 'precipitation', 'both']) {
    const h = harness(async path => {
      if (failure === 'both' || (path.includes('/weather/') ? failure === 'weather' : failure === 'precipitation')) throw new Error('upstream')
      return path.includes('/weather/') ? weather : precipitation
    })
    h.controller.setZone({ zone_id: 'test', latitude: 12, longitude: 75 }); await flush()
    const html = await render(h.state())
    assert.equal(h.state().weather === null, failure !== 'precipitation')
    assert.equal(h.state().precipitation === null, failure !== 'weather')
    assert.doesNotMatch(html, /SIMULATED|150\.0|120\.0|94\.0|synthetic/)
    if (failure !== 'weather') assert.match(html, /Live data unavailable\./)
  }
})

test('rapid zone changes abort both requests and stale responses cannot overwrite the current zone', async () => {
  const pending = [], h = harness(() => new Promise(resolve => pending.push(resolve)))
  h.controller.setZone({ zone_id: 'A', latitude: 12, longitude: 75 }); await flush()
  h.controller.setZone({ zone_id: 'B', latitude: 12.00001, longitude: 75 })
  assert.ok(h.calls.every(c => c.options.signal.aborted))
  assert.equal(h.state().weather, null); assert.equal(h.state().precipitation, null)
  assert.equal(h.state().weatherLoading, true)
  h.controller.setZone({ zone_id: 'C', latitude: 13, longitude: 76 })
  await h.advance(60000)
  pending[2]({ ...weather, temperature_c: 30 }); pending[3]({ ...precipitation, precipitation_rate: 2 }); await flush()
  pending[0](weather); pending[1](precipitation); await flush()
  assert.equal(h.state().zoneId, 'C'); assert.equal(h.state().weather.temperature_c, 30)
  assert.equal(h.state().precipitation.precipitation_rate, 2)
  assert.equal(h.calls.length, 4)
})

test('repeated response objects cause no duplicates and existing refresh cadences are reused', async () => {
  const h = harness(), zone = { zone_id: 'test', latitude: 12, longitude: 75 }
  h.controller.setZone(zone); await flush()
  for (let i = 0; i < 20; i++) h.controller.setZone({ ...zone })
  await flush(); assert.equal(h.calls.length, 2)
  await h.advance(300000); assert.equal(h.calls.length, 3)
  await h.advance(600000); assert.equal(h.calls.length, 6)
  h.controller.dispose(); assert.equal(h.timers.size, 0)
  await h.advance(900000); assert.equal(h.calls.length, 6)
})

test('live display requests and observations leave backend risk and recommendations unchanged', async () => {
  const response = { zone: { zone_id: 'test', latitude: 12, longitude: 75 },
    environmentalValues: { rainfall: { value: 150, status: 'SIMULATED' } }, weatherSource: 'SIMULATED',
    assessment: { overallRisk: 'HIGH', recommendedAction: 'PREVIEW_TARGETED_ALERT', factors: [{ factor: 'rainfall', value: 150 }], dataQuality: 'PARTIAL' } }
  const before = structuredClone(response), intelligence = buildAdminIntelligence(response)
  const h = harness(); h.controller.setZone(intelligence.zone); await flush()
  assert.deepEqual(response, before)
  assert.equal(intelligence.assessment, response.assessment)
  assert.equal(intelligence.overallRisk, 'HIGH'); assert.equal(intelligence.recommendedAction, 'PREVIEW_TARGETED_ALERT')
  assert.doesNotMatch(await render(h.state()), /SIMULATED|150\.0 mm/)
  assert.ok(h.calls.every(c => !c.options.body && !c.options.method && !c.path.includes('predict')))
  const source = await readFile(new URL('../pages/Admin.jsx', import.meta.url), 'utf8')
  assert.match(source, /liveZone = zoneIntelligence\?\.zone/)
  assert.match(source, /AdminEnvironmentalSignals environment=\{liveEnvironment\}/)
  assert.doesNotMatch(source, /const values = intelligence\.environmentalValues/)
  assert.doesNotMatch(source, /navigator\.geolocation|predict-risk/)
})
