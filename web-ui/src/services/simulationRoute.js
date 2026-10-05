import { distanceMeters } from './incidentDemo.js'

// Split a segment at every polygon edge and test each open interval. This
// catches crossings even when both endpoints are outside (a point-only check cannot).
export function segmentCuts(a, b, ring) {
  const cuts = [0, 1]
  const dx = b.longitude - a.longitude, dy = b.latitude - a.latitude
  for (let i = 0; i < ring.length - 1; i++) {
    const [x, y] = ring[i], [xx, yy] = ring[i + 1]
    const ex = xx - x, ey = yy - y, denominator = dx * ey - dy * ex
    if (Math.abs(denominator) < 1e-16) continue
    const t = ((x - a.longitude) * ey - (y - a.latitude) * ex) / denominator
    const u = ((x - a.longitude) * dy - (y - a.latitude) * dx) / denominator
    if (t > 1e-7 && t < 1 - 1e-7 && u >= 0 && u <= 1) cuts.push(t)
  }
  cuts.sort((x, y) => x - y)
  return cuts
}

export function segmentEntersDanger(a, b, ring, contains) {
  const cuts = segmentCuts(a, b, ring)
  const dx = b.longitude - a.longitude, dy = b.latitude - a.latitude
  return cuts.slice(1).some((end, index) => {
    // Coordinate serialization may put an exit a fraction of a millimetre
    // inside its edge. Ignore that numerical sliver, not a real crossing.
    if (Math.hypot(dx, dy) * (end - cuts[index]) < 1e-8) return false
    const t = (cuts[index] + end) / 2
    return contains(a.latitude + dy * t, a.longitude + dx * t, ring)
  })
}

export function boundaryDistance(point, ring) {
  const latScale = 111320, lonScale = latScale * Math.cos(point.latitude * Math.PI / 180)
  let nearest = Infinity
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon, lat] = ring[i], [lon2, lat2] = ring[i + 1]
    const x = (lon - point.longitude) * lonScale, y = (lat - point.latitude) * latScale
    const dx = (lon2 - lon) * lonScale, dy = (lat2 - lat) * latScale
    const t = Math.max(0, Math.min(1, -(x * dx + y * dy) / (dx * dx + dy * dy)))
    nearest = Math.min(nearest, distanceMeters(point, { latitude: lat + (lat2 - lat) * t, longitude: lon + (lon2 - lon) * t }))
  }
  return nearest
}

export function calculateLocalEvacuation(people, ring, config, profile, contains, risk) {
  const affected = people.filter(person => person.inside)
  if (!affected.length) throw new Error('No affected people available for an evacuation origin.')
  const round = n => Number(n.toFixed(9))
  const origin = { latitude: round(affected.reduce((sum, p) => sum + p.latitude, 0) / affected.length),
    longitude: round(affected.reduce((sum, p) => sum + p.longitude, 0) / affected.length) }
  const point = ([longitude, latitude]) => ({ latitude, longitude })
  const candidates = [], rejected = []
  for (const site of profile.safeAreas) {
    const destination = point(site.center), safeRing = site.polygon
    const clearance = boundaryDistance(destination, ring)
    const overlaps = safeRing.some(([lon, lat]) => contains(lat, lon, ring)) || ring.some(([lon, lat]) => contains(lat, lon, safeRing)) ||
      safeRing.slice(1).some((p, j) => segmentEntersDanger(point(safeRing[j]), point(p), ring, contains))
    if (overlaps || clearance < 300 || clearance > 1000 || !site.corridors[risk]) {
      rejected.push(site.id); continue
    }
    const rawPath = [origin, ...site.corridors[risk].map(point)]
    const path = [origin]
    let exitPoint, exitIndex
    for (let i = 1; i < rawPath.length; i++) {
      const a = rawPath[i - 1], b = rawPath[i]
      if (!exitPoint) {
        const cuts = segmentCuts(a, b, ring)
        for (let j = 1; j < cuts.length; j++) {
          const middle = (cuts[j - 1] + cuts[j]) / 2
          if (!contains(a.latitude + (b.latitude - a.latitude) * middle, a.longitude + (b.longitude - a.longitude) * middle, ring)) {
            const t = cuts[j - 1]
            exitPoint = { latitude: round(a.latitude + (b.latitude - a.latitude) * t), longitude: round(a.longitude + (b.longitude - a.longitude) * t) }
            exitIndex = path.length; path.push(exitPoint); break
          }
        }
      }
      path.push(b)
    }
    if (!exitPoint || path.slice(exitIndex + 1).some((p, j) => segmentEntersDanger(path[exitIndex + j], p, ring, contains))) {
      rejected.push(site.id); continue
    }
    const distance = path.slice(1).reduce((sum, p, j) => sum + distanceMeters(path[j], p), 0)
    candidates.push({ path, safeRing, destination, exitPoint, exitIndex, distance, boundaryDistance: clearance,
      safeAreaId: site.id, safeAreaName: site.name, roadNames: site.road_names, osmWayIds: site.osm_way_ids })
  }
  candidates.sort((a, b) => a.distance - b.distance)
  if (!candidates.length) throw new Error('No nearby assembly area has a road corridor outside the danger zone.')
  const best = candidates[0]
  return { ...best, distanceMeters: Math.round(best.distance), boundaryDistanceMeters: Math.round(best.boundaryDistance),
    estimatedMinutes: Math.ceil(best.distance / config.walking_meters_per_minute), candidateCount: candidates.length,
    candidateTotal: profile.safeAreas.length, rejectedCandidates: rejected }
}
