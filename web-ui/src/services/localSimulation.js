import config from '../data/simulationConfig.json' with { type: 'json' }
import { calculateLocalEvacuation } from './simulationRoute.js'

export const SIMULATION_LOCATIONS = Object.keys(config.locations)

// Same ray-casting calculation as geofencing.py. Rings use [longitude, latitude].
export function pointInSimulationPolygon(latitude, longitude, polygon) {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    if ((yi > latitude) !== (yj > latitude) &&
        longitude < (xj - xi) * (latitude - yi) / (yj - yi + 1e-12) + xi) inside = !inside
  }
  return inside
}

export function buildSimulationScenario(location = 'Madikeri', risk = 'HIGH') {
  if (!config.locations[location] || !config.risk_levels.includes(risk)) throw new Error('Unsupported simulation location or risk.')
  const profile = config.locations[location]
  const [lat, lon] = profile.center
  const ring = profile.dangerZones[risk]
  const feature = (name, level, coordinates) => ({
    type: 'Feature', properties: { name, risk_level: level, is_simulation: true },
    geometry: { type: 'Polygon', coordinates: [coordinates] }
  })
  const people = profile.users.map(({ latitude, longitude }, index) => {
    const inside = pointInSimulationPolygon(latitude, longitude, ring)
    return { displayId: `Person ${index + 1}`, latitude, longitude, inside, recipientEligible: inside,
      phone: `+9100000000${String(index + 1).padStart(2, '0')}` }
  })
  const evacuation = calculateLocalEvacuation(people, ring, config.evacuation, profile, pointInSimulationPolygon, risk)
  const message = `SIMULATION ONLY — LANDSENSE ${risk === 'CRITICAL' ? 'CRITICAL ALERT' : 'ALERT'}: ` +
    `You are currently inside the ${location} ${risk.toLowerCase()}-risk danger zone. ` +
    'Evacuate immediately using the recommended safe route to the simulated assembly area. ' +
    'Stay away from unstable slopes and follow official safety instructions. Do not return until the area is declared safe.'
  return { location, risk, center: [lat, lon], people, message, note: config.note,
    dangerZone: feature(location, risk, ring),
    safeZone: feature(evacuation.safeAreaName, 'SAFE', evacuation.safeRing),
    route: { route: { status: 'ok', path: evacuation.path, distance_meters: evacuation.distanceMeters,
      estimated_minutes: evacuation.estimatedMinutes, boundary_distance_meters: evacuation.boundaryDistanceMeters,
      exit_point: evacuation.exitPoint, exit_index: evacuation.exitIndex, candidate_count: evacuation.candidateCount,
      candidate_total: evacuation.candidateTotal, rejected_candidates: evacuation.rejectedCandidates,
      safe_area_id: evacuation.safeAreaId, road_names: evacuation.roadNames, osm_way_ids: evacuation.osmWayIds },
      safe_zone: { name: evacuation.safeAreaName, ...evacuation.destination }, is_simulation: true }
  }
}
