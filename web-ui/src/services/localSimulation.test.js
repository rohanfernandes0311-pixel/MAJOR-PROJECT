import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { buildSimulationScenario, pointInSimulationPolygon, SIMULATION_LOCATIONS } from './localSimulation.js'
import { segmentEntersDanger } from './simulationRoute.js'

test('local map data matches backend geofencing and exports for all ten scenarios', () => {
  const backend = JSON.parse(execFileSync('python', ['-c',
    'import json; from services.simulation_demonstration import CONFIG, build_scenario; print(json.dumps([build_scenario(l,r) for l in CONFIG["locations"] for r in CONFIG["risk_levels"]]))'],
  { cwd: new URL('../../../', import.meta.url), encoding: 'utf8' }))
  for (const server of backend) {
    const local = buildSimulationScenario(server.location, server.risk)
    for (const key of ['people', 'dangerZone', 'safeZone', 'route', 'message']) assert.deepEqual(local[key], server[key])
    assert.equal(local.people.filter(p => p.inside).length, 4)
    assert.equal(local.people.filter(p => !p.inside).length, 4)
  }
  const high = buildSimulationScenario()
  const critical = buildSimulationScenario('Madikeri', 'CRITICAL')
  assert.notDeepEqual(critical.dangerZone.geometry, high.dangerZone.geometry)
  assert.equal(pointInSimulationPolygon(12, 76, [[75, 11], [77, 11], [77, 13], [75, 13]]), true)
  assert.equal(pointInSimulationPolygon(14, 76, [[75, 11], [77, 11], [77, 13], [75, 13]]), false)
  assert.equal(SIMULATION_LOCATIONS.length, 5)
  assert.notDeepEqual(high.route.route.path, critical.route.route.path)
  assert.notDeepEqual(high.safeZone, critical.safeZone)
  for (const location of SIMULATION_LOCATIONS) {
    for (const risk of ['HIGH', 'CRITICAL']) {
      const scenario = buildSimulationScenario(location, risk)
      const route = scenario.route.route
      assert.ok(route.boundary_distance_meters >= 300 && route.boundary_distance_meters <= 1000)
      assert.ok(route.distance_meters < 2200)
      assert.equal(route.candidate_total, 3)
      assert.ok(route.osm_way_ids.length > 0)
      const ring = scenario.dangerZone.geometry.coordinates[0]
      route.path.slice(route.exit_index + 1).forEach((p, j) => assert.equal(segmentEntersDanger(route.path[route.exit_index + j], p, ring, pointInSimulationPolygon), false))
    }
  }
})

test('each location uses independent geography and risk selects a different valid assembly candidate', () => {
  const directions = new Set()
  const shapes = new Set()
  for (const name of SIMULATION_LOCATIONS) {
    const high = buildSimulationScenario(name, 'HIGH'), critical = buildSimulationScenario(name, 'CRITICAL')
    assert.notEqual(high.route.route.safe_area_id, critical.route.route.safe_area_id)
    assert.ok(critical.route.route.rejected_candidates.includes(high.route.route.safe_area_id))
    assert.equal(high.people.filter(p=>p.inside).length, 4)
    assert.equal(critical.people.filter(p=>p.inside).length, 4)
    const [lat, lon] = high.center
    const safe = high.route.safe_zone
    directions.add(Math.round(Math.atan2(safe.latitude-lat,safe.longitude-lon)*180/Math.PI/45))
    shapes.add(JSON.stringify(high.dangerZone.geometry.coordinates[0].map(([x,y])=>[Math.round((x-lon)*1e6),Math.round((y-lat)*1e6)])))
  }
  assert.ok(directions.size >= 3, 'Road-based destinations must not all use the same direction')
  assert.equal(shapes.size, 5, 'Do not translate one global danger polygon')
})

test('route validation detects crossings with both endpoints outside', () => {
  const ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
  assert.equal(segmentEntersDanger({ latitude: .5, longitude: -1 }, { latitude: .5, longitude: 2 }, ring, pointInSimulationPolygon), true)
  assert.equal(segmentEntersDanger({ latitude: 2, longitude: -1 }, { latitude: 2, longitude: 2 }, ring, pointInSimulationPolygon), false)
})

test('map mounting has no scenario API gate and initialization failures are visible', async () => {
  const page = await readFile(new URL('../pages/SimulationDemo.jsx', import.meta.url), 'utf8')
  const map = await readFile(new URL('../shared/MapView.jsx', import.meta.url), 'utf8')
  assert.match(page, /useMemo\(\(\) => buildSimulationScenario\(location, risk\)/)
  assert.doesNotMatch(page, /visual\/scenario|Loading simulation map|setDemo\(null\)/)
  assert.match(map, /init\(\)\.catch/)
  assert.match(map, /Simulation map failed to initialize\./)
  assert.match(map, /marker\.bindPopup\(popup\)/)
})
