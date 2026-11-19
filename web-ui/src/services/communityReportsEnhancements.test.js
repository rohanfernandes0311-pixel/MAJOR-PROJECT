import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  citizenReportStatusLabel,
  isWithinKarnatakaBounds,
  reportsVisibleOnCitizenMap,
  reverseKarnatakaPlace,
  searchKarnatakaPlaces,
} from './communityReportsFeature.js'

const karnatakaFeature = (overrides = {}) => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [75.73, 12.42] },
  properties: { name: 'Madikeri', state: 'Karnataka', country: 'India', countrycode: 'IN', osm_key: 'place', osm_value: 'town', ...overrides },
})

test('place search requests Photon results within India and the Karnataka bounding box', async () => {
  let requestedUrl
  const results = await searchKarnatakaPlaces('madikeri', {
    fetcher: async (url) => {
      requestedUrl = new URL(url)
      return { ok: true, json: async () => ({ features: [karnatakaFeature()] }) }
    },
  })
  assert.equal(requestedUrl.searchParams.get('countrycode'), 'IN')
  assert.equal(requestedUrl.searchParams.get('bbox'), '74,11.5,78.6,18.5')
  assert.equal(results[0].label, 'Madikeri, Karnataka, India')
  assert.equal(results[0].latitude, 12.42)
})

test('place results and picked coordinates must be in Karnataka, India', async () => {
  assert.equal(isWithinKarnatakaBounds(12.42, 75.73), true)
  assert.equal(isWithinKarnatakaBounds(19.0, 75.73), false)
  const results = await searchKarnatakaPlaces('town', {
    fetcher: async () => ({ ok: true, json: async () => ({ features: [
      karnatakaFeature(),
      karnatakaFeature({ state: 'Kerala' }),
      karnatakaFeature({ countrycode: 'NP' }),
    ] }) }),
  })
  assert.equal(results.length, 1)
  await assert.rejects(reverseKarnatakaPlace(19, 75), /within Karnataka/)
})

test('place search ranks places, deduplicates names and rounded coordinates, and falls back to linear features only', async () => {
  const results = await searchKarnatakaPlaces('madikeri', {
    fetcher: async () => ({ ok: true, json: async () => ({ features: [
      karnatakaFeature({ name: 'Chikkamagaluru-Hassan railway line', osm_key: 'railway', osm_value: 'rail' }),
      karnatakaFeature({ name: 'Vastare', osm_value: 'village', county: 'Chikkamagaluru' }),
      karnatakaFeature({ name: 'VÁSTARE', osm_value: 'village', county: 'Chikkamagaluru' }),
      karnatakaFeature({ name: 'Nearby hamlet', osm_value: 'hamlet', county: 'Chikkamagaluru', city: undefined }),
      { ...karnatakaFeature({ name: 'Same point other label', osm_value: 'village' }), geometry: { type: 'Point', coordinates: [75.73001, 12.42001] } },
    ] }) }),
  })
  assert.equal(results.length, 1)
  assert.match(results[0].label, /Vastare/)
  const fallback = await searchKarnatakaPlaces('railway', {
    fetcher: async () => ({ ok: true, json: async () => ({ features: [
      karnatakaFeature({ name: 'Chikkamagaluru-Hassan railway line', osm_key: 'railway', osm_value: 'rail' }),
    ] }) }),
  })
  assert.equal(fallback.length, 1)
  assert.match(fallback[0].label, /railway line/)
})

test('reverse geocoding validates the selected state and country', async () => {
  const place = await reverseKarnatakaPlace(12.42, 75.73, {
    fetcher: async () => ({ ok: true, json: async () => ({ features: [karnatakaFeature()] }) }),
  })
  assert.equal(place.label, 'Madikeri, Karnataka, India')
  await assert.rejects(reverseKarnatakaPlace(12.42, 75.73, {
    fetcher: async () => ({ ok: true, json: async () => ({ features: [karnatakaFeature({ state: 'Kerala' })] }) }),
  }), /outside Karnataka/)
})

test('the enhanced citizen map displays verified reports only and the flag restores old visibility', () => {
  const reports = [{ status: 'pending' }, { status: 'under_review' }, { status: 'verified' }, { status: 'rejected' }]
  assert.deepEqual(reportsVisibleOnCitizenMap(reports, true), [{ status: 'verified' }])
  assert.deepEqual(reportsVisibleOnCitizenMap(reports, false), reports)
  assert.equal(citizenReportStatusLabel(undefined, true), 'Pending')
  assert.equal(citizenReportStatusLabel('under_review', true), 'Pending')
  assert.equal(citizenReportStatusLabel('verified', true), 'Approved')
  assert.equal(citizenReportStatusLabel('rejected', true), 'Rejected')
  assert.equal(citizenReportStatusLabel('verified', false), 'Verified')
})

test('citizen place picker keeps the current payload shape and required controls', async () => {
  const [component, map] = await Promise.all([
    readFile(new URL('../components/CommunityReports.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../components/CommunityReportLocationMap.jsx', import.meta.url), 'utf8'),
  ])
  assert.match(component, /Search place/)
  assert.match(component, /Use my current location/)
  assert.match(component, /No places found/)
  assert.match(component, /setTimeout\(\(\) => \{/)
  assert.match(component, /console\.error\('Community report submission failed'/)
  assert.match(component, /CommunityReportLocationMap/)
  assert.match(component, /latitude: Number\(form\.latitude\)/)
  assert.match(component, /longitude: Number\(form\.longitude\)/)
  assert.match(component, /locationIsValid/)
  assert.match(map, /draggable: true/)
  assert.match(map, /map\.on\('click'/)
  assert.match(component, /Landslide/)
  assert.match(component, /Road blockage due to landslide/)
  assert.match(component, /Cracks or ground movement/)
})
