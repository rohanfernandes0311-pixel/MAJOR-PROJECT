"""Offline local evacuation corridor, mirrored by the browser implementation."""
import math

from geofencing import point_in_polygon
from route_planner import haversine_km


def segment_cuts(a, b, ring):
    cuts = [0, 1]
    dx, dy = b['longitude'] - a['longitude'], b['latitude'] - a['latitude']
    for (x, y), (xx, yy) in zip(ring, ring[1:]):
        ex, ey = xx - x, yy - y
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-16:
            continue
        t = ((x - a['longitude']) * ey - (y - a['latitude']) * ex) / denominator
        u = ((x - a['longitude']) * dy - (y - a['latitude']) * dx) / denominator
        if 1e-7 < t < 1 - 1e-7 and 0 <= u <= 1:
            cuts.append(t)
    cuts.sort()
    return cuts


def segment_enters_danger(a, b, ring):
    cuts = segment_cuts(a, b, ring)
    dx, dy = b['longitude'] - a['longitude'], b['latitude'] - a['latitude']
    return any(point_in_polygon(a['latitude'] + dy * ((start + end) / 2), a['longitude'] + dx * ((start + end) / 2), ring)
               for start, end in zip(cuts, cuts[1:]) if math.hypot(dx,dy)*(end-start) >= 1e-8)


def boundary_distance(point, ring):
    lat_scale, lon_scale = 111320, 111320 * math.cos(math.radians(point['latitude']))
    nearest = float('inf')
    for (lon, lat), (lon2, lat2) in zip(ring, ring[1:]):
        x, y = (lon-point['longitude'])*lon_scale, (lat-point['latitude'])*lat_scale
        dx, dy = (lon2-lon)*lon_scale, (lat2-lat)*lat_scale
        t = max(0,min(1,-(x*dx+y*dy)/(dx*dx+dy*dy)))
        nearest = min(nearest,haversine_km(point['latitude'],point['longitude'],lat+(lat2-lat)*t,lon+(lon2-lon)*t)*1000)
    return nearest


def calculate_local_evacuation(people, ring, config, profile, risk):
    affected = [p for p in people if p['inside']]
    if not affected:
        raise ValueError('No affected people available for an evacuation origin.')
    origin = {'latitude':round(sum(p['latitude'] for p in affected)/len(affected),9),
              'longitude':round(sum(p['longitude'] for p in affected)/len(affected),9)}
    def point(pair): return {'latitude':pair[1],'longitude':pair[0]}
    candidates, rejected = [], []
    for site in profile['safeAreas']:
        destination, safe_ring = point(site['center']), site['polygon']
        clearance = boundary_distance(destination,ring)
        overlaps = (any(point_in_polygon(lat,lon,ring) for lon,lat in safe_ring) or
                    any(point_in_polygon(lat,lon,safe_ring) for lon,lat in ring) or
                    any(segment_enters_danger(point(a),point(b),ring) for a,b in zip(safe_ring,safe_ring[1:])))
        if overlaps or not 300 <= clearance <= 1000 or risk not in site['corridors']:
            rejected.append(site['id']); continue
        raw_path = [origin,*map(point,site['corridors'][risk])]
        path, exit_point, exit_index = [origin], None, None
        for a,b in zip(raw_path,raw_path[1:]):
            if exit_point is None:
                cuts = segment_cuts(a,b,ring)
                for start,end in zip(cuts,cuts[1:]):
                    middle=(start+end)/2
                    if not point_in_polygon(a['latitude']+(b['latitude']-a['latitude'])*middle,a['longitude']+(b['longitude']-a['longitude'])*middle,ring):
                        exit_point={'latitude':round(a['latitude']+(b['latitude']-a['latitude'])*start,9),
                                    'longitude':round(a['longitude']+(b['longitude']-a['longitude'])*start,9)}
                        exit_index=len(path); path.append(exit_point); break
            path.append(b)
        if exit_point is None or any(segment_enters_danger(a,b,ring) for a,b in zip(path[exit_index:],path[exit_index+1:])):
            rejected.append(site['id']); continue
        total=sum(haversine_km(a['latitude'],a['longitude'],b['latitude'],b['longitude'])*1000 for a,b in zip(path,path[1:]))
        candidates.append({'path':path,'safe_ring':safe_ring,'destination':destination,'exit_point':exit_point,'exit_index':exit_index,
                           'distance':total,'boundary_distance':clearance,'safe_area_id':site['id'],'safe_area_name':site['name'],
                           'road_names':site['road_names'],'osm_way_ids':site['osm_way_ids']})
    if not candidates:
        raise ValueError('No nearby assembly area has a road corridor outside the danger zone.')
    best=min(candidates,key=lambda c:c['distance'])
    return {**best,'distance_meters':round(best['distance']),'boundary_distance_meters':round(best['boundary_distance']),
            'estimated_minutes':math.ceil(best['distance']/config['walking_meters_per_minute']),
            'candidate_count':len(candidates),'candidate_total':len(profile['safeAreas']),'rejected_candidates':rejected}
