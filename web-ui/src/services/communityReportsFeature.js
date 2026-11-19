export const COMMUNITY_REPORTS_ENHANCED = import.meta.env?.VITE_COMMUNITY_REPORTS_ENHANCED !== 'false'

export const KARNATAKA_BOUNDS = Object.freeze({
  south: 11.5,
  north: 18.5,
  west: 74.0,
  east: 78.6,
})

export function isWithinKarnatakaBounds(latitude, longitude) {
  const lat = Number(latitude)
  const lng = Number(longitude)
  return Number.isFinite(lat) && Number.isFinite(lng)
    && lat >= KARNATAKA_BOUNDS.south && lat <= KARNATAKA_BOUNDS.north
    && lng >= KARNATAKA_BOUNDS.west && lng <= KARNATAKA_BOUNDS.east
}

function isKarnatakaFeature(feature) {
  const properties = feature?.properties || {}
  const [longitude, latitude] = feature?.geometry?.coordinates || []
  return String(properties.countrycode || '').toUpperCase() === 'IN'
    && String(properties.state || '').trim().toLowerCase() === 'karnataka'
    && isWithinKarnatakaBounds(latitude, longitude)
}

const PLACE_PRIORITY = new Map([
  ['city', 0], ['town', 1], ['village', 2], ['suburb', 3], ['hamlet', 4],
  ['locality', 5], ['neighbourhood', 5], ['neighborhood', 5], ['quarter', 5],
  ['taluk', 6], ['tehsil', 6], ['district', 6], ['county', 7],
])
const LINEAR_KEYS = new Set(['railway', 'highway', 'power', 'waterway', 'route'])

function placeFromFeature(feature) {
  if (!isKarnatakaFeature(feature)) return null
  const [longitude, latitude] = feature.geometry.coordinates
  const properties = feature.properties || {}
  const osmKey = String(properties.osm_key || '').toLowerCase()
  const osmValue = String(properties.osm_value || '').toLowerCase()
  const type = String(properties.type || '').toLowerCase()
  const linear = LINEAR_KEYS.has(osmKey) || LINEAR_KEYS.has(osmValue) || type === 'line'
  const kind = PLACE_PRIORITY.has(osmValue) ? osmValue : PLACE_PRIORITY.has(type) ? type : ''
  if (!kind && !linear) return null
  const parts = [properties.name, properties.city, properties.county, properties.state, properties.country]
    .map((part) => String(part || '').trim())
    .filter((part, index, values) => part && values.indexOf(part) === index)
  return {
    latitude: Number(latitude),
    longitude: Number(longitude),
    label: parts.join(', ') || 'Selected place, Karnataka, India',
    priority: kind ? PLACE_PRIORITY.get(kind) : 100,
    linear,
  }
}

function normalizePlaceName(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

async function photonRequest(path, parameters, { signal, fetcher = fetch } = {}) {
  const url = new URL(`https://photon.komoot.io/${path}`)
  Object.entries(parameters).forEach(([key, value]) => url.searchParams.set(key, String(value)))
  const response = await fetcher(url, { signal, headers: { Accept: 'application/geo+json, application/json' } })
  if (!response.ok) throw new Error('Place search is unavailable. Please try again.')
  return response.json()
}

export async function searchKarnatakaPlaces(query, options = {}) {
  const search = String(query || '').trim()
  if (search.length < 3) return []
  const { west, south, east, north } = KARNATAKA_BOUNDS
  const response = await photonRequest('api', {
    q: search,
    countrycode: 'IN',
    bbox: `${west},${south},${east},${north}`,
    limit: 20,
    lang: 'en',
  }, options)
  const places = (Array.isArray(response?.features) ? response.features : [])
    .map(placeFromFeature)
    .filter(Boolean)
    .sort((a, b) => a.priority - b.priority)
  const preferredPlaces = places.filter((place) => !place.linear)
  const candidates = preferredPlaces.length ? preferredPlaces : places
  const names = new Set()
  const coordinates = new Set()
  return candidates.filter((place) => {
    const name = normalizePlaceName(place.label)
    const point = `${place.latitude.toFixed(4)},${place.longitude.toFixed(4)}`
    if (!name || names.has(name) || coordinates.has(point)) return false
    names.add(name)
    coordinates.add(point)
    return true
  }).slice(0, 8)
}

export async function reverseKarnatakaPlace(latitude, longitude, options = {}) {
  const lat = Number(latitude)
  const lng = Number(longitude)
  if (!isWithinKarnatakaBounds(lat, lng)) {
    throw new Error('Choose a location within Karnataka, India.')
  }
  const response = await photonRequest('reverse', { lat, lon: lng, lang: 'en' }, options)
  const place = (Array.isArray(response?.features) ? response.features : [])
    .map(placeFromFeature)
    .find(Boolean)
  if (!place) throw new Error('This point is outside Karnataka or could not be identified. Choose a place in Karnataka.')
  return place
}

export function reportsVisibleOnCitizenMap(reports, enhanced = COMMUNITY_REPORTS_ENHANCED) {
  const list = Array.isArray(reports) ? reports : []
  return enhanced ? list.filter((report) => String(report?.status || 'pending').toLowerCase() === 'verified') : list
}

export function citizenReportStatusLabel(status, enhanced = COMMUNITY_REPORTS_ENHANCED) {
  const value = String(status || 'pending').toLowerCase()
  if (!enhanced) return ({ pending: 'Pending', under_review: 'Under Review', verified: 'Verified', rejected: 'Rejected' })[value] || value
  if (value === 'verified') return 'Approved'
  if (value === 'under_review' || value === 'pending') return 'Pending'
  if (value === 'rejected') return 'Rejected'
  return 'Pending'
}
