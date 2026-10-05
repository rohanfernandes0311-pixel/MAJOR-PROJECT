"""One-time read-only OSM extraction; the demonstration never calls this API."""
import json
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
config = json.loads((BASE / 'web-ui/src/data/simulationConfig.json').read_text())
data = {'source': 'https://api.openstreetmap.org/api/0.6/map', 'license': 'ODbL; © OpenStreetMap contributors', 'locations': {}}
for name, entry in config['locations'].items():
    lat, lon = entry['center'] if isinstance(entry, dict) else entry
    cached = BASE / 'validation/simulation' / f'{name.lower()}-osm.xml'
    if not cached.exists():
        response = requests.get(data['source'], params={'bbox': f'{lon-.022},{lat-.022},{lon+.022},{lat+.022}'}, timeout=45,
                                headers={'User-Agent': 'LandSense-offline-demo-data-preparation/1.0'})
        response.raise_for_status()
        cached.write_bytes(response.content)
    root = ET.parse(cached).getroot()
    nodes = {n.attrib['id']: {'lat': float(n.attrib['lat']), 'lon': float(n.attrib['lon'])} for n in root.findall('node')}
    ways = []
    for way in root.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        if not tags.get('highway') or tags.get('highway') in ['motorway', 'construction', 'proposed'] or tags.get('access') == 'private' or tags.get('foot') == 'no':
            continue
        refs = [n.attrib['ref'] for n in way.findall('nd')]
        if all(ref in nodes for ref in refs):
            ways.append({'id': way.attrib['id'], 'nodes': refs, 'geometry': [nodes[ref] for ref in refs], 'tags': tags})
    data['locations'][name] = ways
    print(name, len(ways), 'road ways', flush=True)
output = BASE / 'validation/simulation/osm-roads-source.json'
output.write_text(json.dumps(data), encoding='utf-8')
print('Saved road source snapshots')
