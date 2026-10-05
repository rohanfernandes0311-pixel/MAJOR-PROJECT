"""Prepare explicit offline demo geography from cached OSM roads.

Shapely is used only by this one-time preparation/independent validation script.
It is not an application or browser dependency. Assembly sites are fictional.
"""
import heapq
import json
import math
from pathlib import Path
import sys

from shapely.geometry import Point, Polygon, LineString

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from route_planner import haversine_km

CONFIG_PATH = BASE / 'web-ui/src/data/simulationConfig.json'
old = json.loads(CONFIG_PATH.read_text())
roads = json.loads((BASE / 'validation/simulation/osm-roads-source.json').read_text())
SHAPES = {
 'Madikeri': [[-450,-390],[280,-410],[470,-180],[430,330],[80,480],[-410,300]],
 'Virajpet': [[-430,-240],[100,-450],[400,-310],[530,120],[220,450],[-350,350]],
 'Chittalli': [[-350,-460],[380,-360],[480,190],[190,430],[-460,250]],
 'Perumbadi': [[-420,-280],[220,-510],[500,-180],[410,370],[-300,460],[-520,30]],
 'Makutta': [[-320,-390],[390,-270],[480,270],[-30,470],[-440,180]],
}
USERS = {
 'Madikeri': [[-60,90],[150,-70],[-100,-140],[90,140],[-1150,450],[900,1200],[1300,-500],[-950,-1000]],
 'Virajpet': [[-130,60],[70,-120],[120,80],[-40,-90],[-1100,700],[1250,900],[-800,-1200],[1400,-600]],
 'Chittalli': [[70,110],[-140,-70],[160,-90],[-90,130],[-1000,950],[1300,500],[800,-1300],[-1350,-600]],
 'Perumbadi': [[-110,100],[140,-130],[40,120],[-80,-100],[-1250,400],[1000,1200],[1450,-400],[-900,-1250]],
 'Makutta': [[-60,130],[140,10],[-130,-110],[70,-160],[-1100,850],[1150,1200],[1350,-700],[-950,-1200]],
}
result = {'note': 'Fictional hazard boundaries, people and assembly sites. Corridors use cached OpenStreetMap road geometry; suitability and road access are not verified for a real emergency.',
          'risk_levels': ['HIGH','CRITICAL'], 'evacuation': {'walking_meters_per_minute':75},
          'provenance': {'source': roads['source'], 'license': roads['license'], 'retrieved_date':'2026-10-04',
                         'runtime_network_required': False}, 'locations': {}}
for name, entry in old['locations'].items():
    lat, lon = entry['center'] if isinstance(entry,dict) else entry
    # The original approximate centers in these rural demos were off the mapped
    # road. Anchor their synthetic footprint to an actual local road waypoint.
    lat, lon = {'Chittalli':(12.37967,75.8382414),'Perumbadi':(12.1438484,75.7946475),
                'Makutta':(12.081075,75.7524061)}.get(name,(lat,lon))
    lat_scale, lon_scale = 111320, 111320 * math.cos(math.radians(lat))
    def coordinate(x,y): return [round(lon+x/lon_scale,9), round(lat+y/lat_scale,9)]
    def project(point): return [(point[0]-lon)*lon_scale,(point[1]-lat)*lat_scale]
    def distance(a,b): return haversine_km(a[1],a[0],b[1],b[0])*1000
    high = SHAPES[name]
    # Distinct affected footprints are explicit in the resulting configuration.
    expansion = {'Madikeri':1.65,'Virajpet':1.7,'Chittalli':1.6,'Perumbadi':1.62,'Makutta':1.68}[name]
    rings = {risk: [coordinate(x*(expansion if risk=='CRITICAL' else 1),y*(expansion if risk=='CRITICAL' else 1)) for x,y in high] for risk in result['risk_levels']}
    for ring in rings.values(): ring.append(ring[0])
    polygons = {risk: Polygon([project(p) for p in ring]) for risk,ring in rings.items()}
    people = [{'latitude':coordinate(x,y)[1],'longitude':coordinate(x,y)[0]} for x,y in USERS[name]]
    origin = [sum(p['longitude'] for p in people[:4])/4,sum(p['latitude'] for p in people[:4])/4]
    graph, coordinates, edge_way = {}, {}, {}
    ways = roads['locations'][name]
    way_by_id = {w['id']:w for w in ways}
    for way in ways:
        for node, p in zip(way['nodes'],way['geometry']):
            coordinates[node]=[p['lon'],p['lat']]
            graph.setdefault(node,{})
        for a,b in zip(way['nodes'],way['nodes'][1:]):
            weight = distance(coordinates[a],coordinates[b])
            graph[a][b]=weight; graph[b][a]=weight
            edge_way[(a,b)]=edge_way[(b,a)]=way['id']
    root = min((n for n in graph if polygons['HIGH'].contains(Point(project(coordinates[n])))),key=lambda n:distance(origin,coordinates[n]))
    searches = {}
    for risk, polygon in polygons.items():
        distances, previous, queue = {root:0}, {}, [(0,root)]
        interior = polygon.buffer(-.001)
        while queue:
            cost,node = heapq.heappop(queue)
            if cost!=distances[node] or cost>2400: continue
            outside = not polygon.covers(Point(project(coordinates[node])))
            for neighbor,weight in graph[node].items():
                line = LineString([project(coordinates[node]),project(coordinates[neighbor])])
                if outside and not line.intersection(interior).is_empty: continue
                next_cost=cost+weight
                if next_cost<distances.get(neighbor,float('inf')):
                    distances[neighbor]=next_cost; previous[neighbor]=node; heapq.heappush(queue,(next_cost,neighbor))
        searches[risk]=(distances,previous)
    def clearance(node,risk): return polygons[risk].distance(Point(project(coordinates[node])))
    def safe_ring(node):
        x,y=project(coordinates[node]); size=35
        return [coordinate(x+dx,y+dy) for dx,dy in [(-size,-size),(size,-size),(size,size),(-size,size),(-size,-size)]]
    def valid(node,risk):
        return node in searches[risk][0] and 305<=clearance(node,risk)<=990 and Polygon([project(p) for p in safe_ring(node)]).disjoint(polygons[risk])
    selected=[]
    # Candidate A is the closest local road site for HIGH. B/C provide spatially
    # separate alternatives outside the larger CRITICAL footprint.
    pools=[(lambda n:valid(n,'HIGH') and clearance(n,'CRITICAL')<300,'HIGH'),
           (lambda n:valid(n,'CRITICAL') and valid(n,'HIGH'),'CRITICAL'),
           (lambda n:valid(n,'CRITICAL'),'CRITICAL')]
    for predicate,risk in pools:
        pool=[n for n in graph if predicate(n) and all(distance(coordinates[n],coordinates[s])>250 for s in selected)]
        if not pool: raise RuntimeError(f'{name}: no candidate in {risk} pool')
        # Prefer a mapped junction when comparably close; otherwise use a mapped
        # road waypoint, never an invented off-road coordinate.
        selected.append(min(pool,key=lambda n:searches[risk][0][n]+(0 if len(graph[n])>=3 else 40)))
    candidates=[]
    for index,node in enumerate(selected):
        corridors, way_ids = {}, set()
        for risk in result['risk_levels']:
            if node not in searches[risk][0]: continue
            path_nodes=[node]
            while path_nodes[-1]!=root: path_nodes.append(searches[risk][1][path_nodes[-1]])
            path_nodes.reverse()
            way_ids.update(edge_way[(a,b)] for a,b in zip(path_nodes,path_nodes[1:]))
            corridors[risk]=[coordinates[n] for n in path_nodes]
        names=sorted({way_by_id[w]['tags'].get('name') or way_by_id[w]['tags'].get('ref') or f"Mapped {way_by_id[w]['tags']['highway']} road" for w in way_ids})
        candidates.append({'id':f'{name.lower()}-assembly-{index+1}', 'name':f'{name} {chr(65+index)} — {names[0]} (demo)',
                           'center':coordinates[node], 'polygon':safe_ring(node), 'corridors':corridors,
                           'osm_way_ids':sorted(way_ids), 'road_names':names,'osm_node_id':node})
    result['locations'][name]={'center':[lat,lon], 'dangerZones':rings,'users':people,'safeAreas':candidates}
    print(name, 'road snap',round(distance(origin,coordinates[root])),'m;',[(c['name'],round(clearance(n,'HIGH')),round(clearance(n,'CRITICAL'))) for c,n in zip(candidates,selected)])
CONFIG_PATH.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
