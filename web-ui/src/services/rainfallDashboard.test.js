import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transform } from 'esbuild'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const source = await readFile(new URL('../components/RainfallDashboard.jsx', import.meta.url), 'utf8')
const jsx = source.replace(/^import .*$/gm, '').replace('export default function RainfallDashboard', 'function RainfallDashboard')
const compiled = await transform(jsx, { loader: 'jsx', jsx: 'transform' })
const RainfallDashboard = new Function('React', 'useMemo', 'Bar', 'BarChart', 'CartesianGrid', 'ResponsiveContainer', 'Tooltip', 'XAxis', 'YAxis', `${compiled.code}\nreturn RainfallDashboard;`)(React, React.useMemo, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis)

test('rainfall dashboard labels satellite estimates, gaps, forecast provenance and risk limitations', () => {
  const trends = { available: true, period: 'daily', records: [
    { date: '2026-08-01', rainfall_mm: 2.4 }, { date: '2026-08-02', rainfall_mm: null },
  ], source: 'NASA POWER IMERG_PRECTOT (satellite estimate)', unit: 'mm/day', resolution: '0.1° (~10 km)', updated_at: '2026-08-03T00:00:00Z' }
  const forecast = { available: true, records: [{ date: '2026-11-17', rainfall_mm: 1.2 }], source: 'Weatherbit daily forecast', forecast_start: '2026-11-17', forecast_end: '2026-11-17', updated_at: '2026-11-16T00:00:00Z', attribution_url: 'https://www.weatherbit.io/', note: 'Forecast values are model guidance.' }
  const html = renderToStaticMarkup(React.createElement(RainfallDashboard, { trends, forecast, loading: false, error: false }))
  for (const label of ['Rainfall trends and forecast', 'satellite estimate', 'Missing or incomplete periods', 'Forecast', 'Weatherbit attribution', 'does not change the landslide risk assessment']) assert.ok(html.includes(label), label)
})

test('unavailable rainfall never renders as zero', () => {
  const html = renderToStaticMarkup(React.createElement(RainfallDashboard, { trends: { available: false, records: [] }, forecast: { available: false, records: [] }, loading: false, error: false }))
  assert.match(html, /No historical observations are available/)
  assert.match(html, /Forecast is unavailable/)
  assert.doesNotMatch(html, />0 mm</)
})

test('citizen dashboard calls only the additive authenticated rainfall endpoints for its active GPS fix', async () => {
  const page = await readFile(new URL('../pages/Public.jsx', import.meta.url), 'utf8')
  assert.match(page, /\/citizen\/rainfall\/trends\?latitude=\$\{lat\}&longitude=\$\{lng\}&days=\$\{rainfallDays\}&period=\$\{rainfallPeriod\}/)
  assert.match(page, /\/citizen\/rainfall\/forecast\?latitude=\$\{lat\}&longitude=\$\{lng\}/)
  assert.match(page, /<RainfallDashboard trends=\{rainfallTrends\}/)
  assert.match(page, /return \(\) => controller\.abort\(\)/)
})
