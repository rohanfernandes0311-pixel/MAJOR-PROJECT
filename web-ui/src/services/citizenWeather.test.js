import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transform } from 'esbuild'
import { createCitizenWeatherController, validWeatherLocation, weatherFields, WEATHER_UNAVAILABLE } from './citizenWeather.js'

// Provider responses are isolated test fixtures, never application defaults.
const observation = { source: 'weatherbit', temperature_c: 24.8, humidity_pct: 42, wind_speed_mps: 2.2, visibility_km: 16, precipitation_mm_per_hour: 0, description: 'Few clouds', observed_at: '2026-06-02T16:50:00Z' }
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve() }

function harness(request = async () => observation) {
  let time = 0
  let nextId = 0
  const timers = new Map()
  const calls = []
  const states = []
  const controller = createCitizenWeatherController({
    request: (...args) => { calls.push(args); return request(...args) },
    onChange: state => states.push(state),
    now: () => time,
    setTimer: (callback, delay) => { const id = ++nextId; timers.set(id, { callback, at: time + delay }); return id },
    clearTimer: id => timers.delete(id),
  })
  return {
    controller, calls, states, timers,
    state: () => states.at(-1),
    async advance(ms) {
      const end = time + ms
      for (;;) {
        const due = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
        if (!due) break
        time = due[1].at
        timers.delete(due[0])
        due[1].callback()
        await flush()
      }
      time = end
      await flush()
    },
  }
}

test('no request is made without finite, in-range browser coordinates', async () => {
  const h = harness()
  for (const location of [null, {}, { lat: null, lng: null }, { lat: NaN, lng: 75 }, { lat: 12, lng: Infinity }, { lat: 91, lng: 75 }, { lat: 12, lng: -181 }, { lat: '12', lng: 75 }]) {
    assert.equal(validWeatherLocation(location), false)
    h.controller.setLocation(location)
  }
  await h.advance(600000)
  assert.equal(h.calls.length, 0)
  assert.deepEqual(h.state(), { weather: null, loading: false, error: WEATHER_UNAVAILABLE })
})

test('the first valid browser fix starts a weather request with exactly those coordinates', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 12.42, lng: 75.73, accuracy: 15 })
  assert.equal(h.state().loading, true)
  await flush()
  assert.deepEqual(h.calls[0].slice(0, 2), [12.42, 75.73])
  assert.ok(h.calls[0][2] instanceof AbortSignal)
  assert.deepEqual(h.state(), { weather: observation, loading: false, error: '' })
  h.controller.dispose()
})

test('zero latitude and longitude are valid supplied coordinates', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 0, lng: 0 })
  await flush()
  assert.deepEqual(h.calls[0].slice(0, 2), [0, 0])
  h.controller.dispose()
})

test('Weatherbit measurements and genuine zero values are formatted for the card', () => {
  const fields = Object.fromEntries(weatherFields(observation).map(field => [field.label, field.value]))
  assert.equal(fields.Temperature, '24.8 °C')
  assert.equal(fields.Weather, 'Few clouds')
  assert.equal(fields.Humidity, '42 %')
  assert.equal(fields['Wind speed'], '2.2 m/s')
  assert.equal(fields.Visibility, '16.0 km')
  assert.equal(fields.Precipitation, '0.0 mm/h')
  assert.notEqual(fields.Observed, 'Unavailable')
})

test('missing fields are displayed as Unavailable without manufacturing zeros', () => {
  for (const fields of [weatherFields({ source: 'weatherbit' }), weatherFields(null)]) {
    assert.ok(fields.every(field => field.value === 'Unavailable'))
  }
  const fields = weatherFields({ temperature_c: NaN, humidity_pct: '42', observed_at: 'invalid' })
  assert.ok(fields.every(field => field.value === 'Unavailable'))
})

test('the actual dashboard weather section renders returned values, missing fields, loading and failure', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  const card = source.slice(source.indexOf('function WeatherCard('), source.indexOf('function AlertRiskPill('))
  const start = source.indexOf('<section aria-labelledby="citizen-weather-title"')
  assert.ok(start >= 0)
  const section = source.slice(start, source.indexOf('</section>', start) + '</section>'.length)
  const compiled = await transform(`${card}\nreturn function WeatherSection({ weather, weatherLoading, weatherError }) { return (${section}) }`, { loader: 'jsx', jsx: 'transform' })
  const WeatherSection = new Function('React', 'weatherFields', 'WEATHER_UNAVAILABLE', compiled.code)(React, weatherFields, WEATHER_UNAVAILABLE)
  const render = props => renderToStaticMarkup(React.createElement(WeatherSection, { weatherLoading: false, weatherError: '', ...props }))
  const success = render({ weather: observation })
  for (const value of ['24.8 °C', 'Few clouds', '42 %', '2.2 m/s', '16.0 km', '0.0 mm/h', 'Weatherbit']) assert.ok(success.includes(value))
  const partial = render({ weather: { source: 'weatherbit', temperature_c: 24.8 } })
  assert.equal((partial.match(/>Unavailable</g) || []).length, 6)
  assert.ok(render({ weatherLoading: true }).includes('Loading live weather'))
  const failed = render({ weather: null, weatherError: WEATHER_UNAVAILABLE })
  assert.equal(WEATHER_UNAVAILABLE, 'Live weather unavailable.')
  assert.ok(failed.includes('>Live weather unavailable.</p>'))
  assert.ok(!failed.includes('24.8'))
})

test('API failures clear old weather and provide only the safe unavailable message', async () => {
  let fail = false
  const h = harness(async () => { if (fail) throw new Error('private upstream details'); return observation })
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  fail = true
  await h.advance(300000)
  assert.deepEqual(h.state(), { weather: null, loading: false, error: WEATHER_UNAVAILABLE })
  h.controller.dispose()
})

test('responses from another provider cannot substitute for Weatherbit', async () => {
  const h = harness(async () => ({ ...observation, source: 'simulated' }))
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  assert.equal(h.state().error, WEATHER_UNAVAILABLE)
  assert.equal(h.state().weather, null)
  h.controller.dispose()
})

test('duplicate and small GPS movements do not trigger repeated requests', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  for (let i = 0; i < 100; i++) h.controller.setLocation({ lat: 12 + i / 1000000, lng: 75 })
  await h.advance(299999)
  assert.equal(h.calls.length, 1)
  await h.advance(1)
  assert.equal(h.calls.length, 2)
  h.controller.dispose()
})

test('meaningful movement uses the newest fix but enforces a one-minute request limit', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  h.controller.setLocation({ lat: 12.02, lng: 75 })
  h.controller.setLocation({ lat: 12.04, lng: 75 })
  await h.advance(59999)
  assert.equal(h.calls.length, 1)
  await h.advance(1)
  assert.equal(h.calls.length, 2)
  assert.deepEqual(h.calls[1].slice(0, 2), [12.04, 75])
  h.controller.dispose()
})

test('a superseded response cannot replace weather for a newer location', async () => {
  const pending = []
  const h = harness(() => new Promise(resolve => pending.push(resolve)))
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  h.controller.setLocation({ lat: 13, lng: 76 })
  assert.equal(h.calls[0][2].aborted, true)
  await h.advance(60000)
  pending[1]({ ...observation, description: 'New location' })
  await flush()
  pending[0]({ ...observation, description: 'Old location' })
  await flush()
  assert.equal(h.state().weather.description, 'New location')
  h.controller.dispose()
})

test('location loss cancels requests and clears weather without scheduled requests', async () => {
  let resolve
  const h = harness(() => new Promise(done => { resolve = done }))
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  h.controller.setLocation(null)
  assert.equal(h.calls[0][2].aborted, true)
  resolve(observation)
  await h.advance(600000)
  assert.equal(h.state().weather, null)
  assert.equal(h.state().error, WEATHER_UNAVAILABLE)
  assert.equal(h.calls.length, 1)
  assert.equal(h.timers.size, 0)
})

test('unmount cancels timers and prevents late updates', async () => {
  let resolve
  const h = harness(() => new Promise(done => { resolve = done }))
  h.controller.setLocation({ lat: 12, lng: 75 })
  await flush()
  h.controller.dispose()
  const count = h.states.length
  resolve(observation)
  await h.advance(600000)
  assert.equal(h.states.length, count)
  assert.equal(h.calls[0][2].aborted, true)
  assert.equal(h.timers.size, 0)
})

test('a lost fix before the queued request starts never sends invented or obsolete coordinates', async () => {
  const h = harness()
  h.controller.setLocation({ lat: 12, lng: 75 })
  h.controller.setLocation(null)
  await flush()
  assert.equal(h.calls.length, 0)
})

test('Citizen weather is independent of prediction/geofence/map handling and reuses the existing watcher', async () => {
  const source = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.equal((source.match(/navigator\.geolocation\.watchPosition\(/g) || []).length, 1)
  assert.match(source, /weatherControllerRef\.current\?\.setLocation\(location\)/)
  assert.match(source, /fetchJson\(`\/citizen\/weather\/current\?latitude=\$\{lat\}&longitude=\$\{lng\}`, \{ signal, cache: 'no-store' \}\)/)
  const evaluation = source.slice(source.indexOf('const evaluatePosition ='), source.indexOf('const checkSafetyOnce ='))
  assert.doesNotMatch(evaluation, /setWeather|weatherError|weatherLoading/)
  assert.match(evaluation, /prediction = await tryPredict\(lat, lng\)/)
  assert.match(evaluation, /deriveCitizenGeofenceState\(prediction\)/)
  assert.match(evaluation, /fetchJson\('\/location-update'/)
  assert.match(source, /userLocation=\{location\}/)
  assert.doesNotMatch(source, /prediction\?\.weather|prediction\.weather|VITE_WEATHERBIT|api\.weatherbit\.io/)
  assert.match(source, /weatherFields\(weather\)\.map/)
  assert.match(source, /weatherError \|\| !weather/)
})

test('development proxy routes the new weather endpoint and existing authenticated requests bypass service worker cache', async () => {
  const proxy = await readFile(new URL('../../vite.config.js', import.meta.url), 'utf8')
  const worker = await readFile(new URL('../../public/sw.js', import.meta.url), 'utf8')
  assert.match(proxy, /'\/citizen\/weather'/)
  assert.match(worker, /req\.headers\.has\('Authorization'\)/)
})
