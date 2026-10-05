"""Local browser verification with fixture auth and no production database access.

Run after npm run build. Serves only on loopback and stops when checks finish.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from openpyxl import load_workbook
from websockets.sync.client import connect

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.auth.middleware import get_current_user
from services.simulation_demonstration import CONFIG, router
from services.simulation_demonstration import build_scenario


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    output = BASE / 'validation' / 'simulation'
    output.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {'role': 'Admin'}
    requests = []
    scenario_available = True

    @app.middleware('http')
    async def record(request: Request, call_next):
        requests.append((request.method, request.url.path))
        if not scenario_available and request.url.path == '/admin/simulation/visual/scenario':
            return JSONResponse({'detail': 'Simulation backend unavailable for browser verification'}, status_code=503)
        return await call_next(request)

    @app.get('/auth/me')
    def profile():
        return {'profile': {'role': 'Admin', 'uid': 'browser-fixture'}}

    @app.get('/{path:path}')
    def fixtures(path: str):
        candidate = BASE / 'web-ui' / 'dist' / path
        if candidate.is_file():
            return FileResponse(candidate)
        if path in ('admin', 'admin/simulation', 'admin/simulation/demo', ''):
            return FileResponse(BASE / 'web-ui' / 'dist' / 'index.html')
        if path == 'admin/simulation/state':
            return {'enabled': False, 'is_simulation': False}
        return {}

    # Only the fixture process receives this sender; runtime configuration is untouched.
    os.environ['HTTPSMS_FROM_NUMBER'] = '+919876543210'
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8766, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    browser = None
    try:
        with tempfile.TemporaryDirectory(prefix='landsense-browser-', ignore_cleanup_errors=True) as profile_dir:
            browser = subprocess.Popen([
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                '--remote-debugging-port=9226', f'--user-data-dir={profile_dir}', 'about:blank'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(100):
                try:
                    targets = json.load(urlopen('http://127.0.0.1:9226/json'))
                    page = next(item for item in targets if item['type'] == 'page')
                    break
                except Exception:
                    time.sleep(.1)
            else:
                raise RuntimeError('Browser did not start')
            events = []
            with connect(page['webSocketDebuggerUrl'], max_size=20_000_000) as ws:
                seq = 0

                def command(method, params=None):
                    nonlocal seq
                    seq += 1
                    ws.send(json.dumps({'id': seq, 'method': method, 'params': params or {}}))
                    while True:
                        reply = json.loads(ws.recv(timeout=20))
                        if reply.get('id') == seq:
                            if 'error' in reply:
                                raise RuntimeError(reply['error'])
                            return reply.get('result', {})
                        events.append(reply)

                def evaluate(expression):
                    reply = command('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
                    if 'exceptionDetails' in reply:
                        raise RuntimeError(reply['exceptionDetails'])
                    return reply['result'].get('value')

                def wait(expression):
                    for _ in range(100):
                        if evaluate(expression):
                            return
                        time.sleep(.1)
                    raise AssertionError(f'Timed out: {expression}')

                command('Runtime.enable')
                command('Log.enable')
                command('Page.enable')
                command('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(output)})
                command('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
                command('Page.addScriptToEvaluateOnNewDocument', {'source': "localStorage.setItem('landsense_auth_token','fixture-token'); localStorage.setItem('landsense_auth_profile',JSON.stringify({role:'Admin',uid:'browser-fixture'}));"})
                command('Page.navigate', {'url': 'http://127.0.0.1:8766/admin'})
                wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='Create Synthetic Zone')")
                evaluate("document.querySelector('section[aria-labelledby=\"kodagu-simulation-heading\"] select').value='Makutta'; document.querySelector('section[aria-labelledby=\"kodagu-simulation-heading\"] select').dispatchEvent(new Event('change',{bubbles:true})); [...document.querySelectorAll('section[aria-labelledby=\"kodagu-simulation-heading\"] button')].find(b=>b.textContent==='CRITICAL').click()")
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Create Synthetic Zone').click()")
                wait("document.body.innerText.includes('Eight fictional people: 4 inside and 4 outside')")
                evaluate("[...document.querySelectorAll('a')].find(a=>a.textContent==='Open Simulation Demonstration').click()")
                wait("location.search.includes('Makutta') && document.querySelectorAll('tbody tr').length===8")
                results = []
                scenario_available = False
                scenario_requests_before = sum(path == '/admin/simulation/visual/scenario' for method, path in requests)
                command('Page.navigate', {'url': 'http://127.0.0.1:8766/admin/simulation'})
                wait("document.querySelectorAll('tbody tr').length===8 && document.querySelector('.leaflet-container canvas')!==null")
                assert evaluate("document.querySelector('section[aria-label=\"Simulation map\"] h2').textContent") == 'MADIKERI · HIGH RISK'
                wait("[...document.querySelectorAll('img.leaflet-tile')].some(t=>t.complete && t.naturalWidth>0)")
                wait("[...document.querySelectorAll('img.leaflet-tile')].every(t=>t.complete && t.naturalWidth>0)")
                image = command('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True})
                (output / 'simulation-map-fixed.png').write_bytes(base64.b64decode(image['data']))
                results.append('Default /admin/simulation: Madikeri HIGH geographical tiles and overlays rendered without scenario backend')
                default_text = evaluate("document.querySelector('section[aria-label=\"Simulation control\"]').innerText")
                default_route = build_scenario('Madikeri','HIGH')['route']['route']
                assert f"{default_route['distance_meters']} m" in default_text and 'Simulation estimate' in default_text
                results.append('Madikeri HIGH: mapped College Road corridor, location-specific destination and walking estimate displayed')
                for name in CONFIG['locations']:
                    evaluate(f"document.querySelector('section[aria-label=\"Simulation control\"] select').value={json.dumps(name)}; document.querySelector('section[aria-label=\"Simulation control\"] select').dispatchEvent(new Event('change',{{bubbles:true}}))")
                    wait(f"document.querySelector('section[aria-label=\"Simulation map\"] h2').textContent.startsWith({json.dumps(name.upper())}) && [...document.querySelectorAll('.leaflet-tooltip')].some(t=>t.textContent.includes({json.dumps(name)}))")
                evaluate("document.querySelectorAll('section[aria-label=\"Simulation control\"] select')[1].value='CRITICAL'; document.querySelectorAll('section[aria-label=\"Simulation control\"] select')[1].dispatchEvent(new Event('change',{bubbles:true}))")
                wait("document.querySelector('section[aria-label=\"Simulation map\"] h2').textContent.includes('CRITICAL RISK')")
                results.append('All five location dropdowns and HIGH → CRITICAL: map overlays updated without scenario backend')

                def click_geographic(latitude, longitude):
                    position = evaluate(fr"""(() => {{
                      const tile = [...document.querySelectorAll('img.leaflet-tile')].find(t=>t.complete && t.naturalWidth>0);
                      const match = tile.src.match(/\/(\d+)\/(\d+)\/(\d+)\.png/);
                      const [z,x,y] = match.slice(1).map(Number), size = 2**z;
                      const lat = {latitude}*Math.PI/180;
                      const px = ({longitude}+180)/360*size, py = (1-Math.log(Math.tan(lat)+1/Math.cos(lat))/Math.PI)/2*size;
                      const rect = tile.getBoundingClientRect();
                      return {{x:rect.left+(px-x)*rect.width,y:rect.top+(py-y)*rect.height}};
                    }})()""")
                    command('Input.dispatchMouseEvent', {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **position})
                    command('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, **position})

                # Click the actual canvas markers, not a mocked popup API.
                wait("[...document.querySelectorAll('img.leaflet-tile')].some(t=>t.complete && t.naturalWidth>0)")
                latitude, longitude = CONFIG['locations']['Makutta']['center']
                inside_person = CONFIG['locations']['Makutta']['users'][0]
                click_geographic(inside_person['latitude'], inside_person['longitude'])
                wait("document.querySelector('.leaflet-popup-content')?.textContent.includes('SMS ELIGIBLE')")
                evaluate("document.querySelector('.leaflet-popup-close-button').click()")
                time.sleep(.5)
                # The scenario now fits the local route, not distant excluded people.
                # Zoom out to inspect the outside marker as a user would.
                evaluate("document.querySelector('.leaflet-control-zoom-out').click()")
                time.sleep(.5)
                outside_person = CONFIG['locations']['Makutta']['users'][4]
                click_geographic(outside_person['latitude'], outside_person['longitude'])
                wait("document.querySelector('.leaflet-popup-content')?.textContent.includes('EXCLUDED')")
                evaluate("document.querySelector('.leaflet-popup-close-button').click()")
                results.append('Actual marker clicks: inside person SMS ELIGIBLE; outside person EXCLUDED')
                time.sleep(.5)
                click_geographic(latitude + .004, longitude + .004)
                wait("document.querySelector('.leaflet-popup-content')?.textContent.includes('Generated synthetic zone')")
                evaluate("document.querySelector('.leaflet-popup-close-button').click()")
                tile_zoom = "Math.max(...[...document.querySelectorAll('img.leaflet-tile')].map(t=>Number(t.src.match(/\\/(\\d+)\\/\\d+\\/\\d+\\.png/)[1])))"
                previous_zoom = evaluate(tile_zoom)
                evaluate("document.querySelector('.leaflet-control-zoom-in').click()")
                wait(f'({tile_zoom}) > {previous_zoom}')
                evaluate("document.querySelector('.leaflet-control-zoom-out').click()")
                wait(f'({tile_zoom}) <= {previous_zoom}')
                position = evaluate("(() => {const r=document.querySelector('.leaflet-container').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2+100}})()")
                before_pan = evaluate("document.querySelector('.leaflet-map-pane').style.transform")
                command('Input.dispatchMouseEvent', {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **position})
                for step in range(1, 6):
                    command('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'button': 'left', 'buttons': 1, 'x': position['x'] + step*16, 'y': position['y'] + step*8})
                command('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, 'x': position['x']+80, 'y': position['y']+40})
                assert evaluate("document.querySelector('.leaflet-map-pane').style.transform") != before_pan
                results.append('Danger-zone click, zoom in/out and actual map panning: verified')
                for location in CONFIG['locations']:
                    for risk in CONFIG['risk_levels']:
                        command('Page.navigate', {'url': f'http://127.0.0.1:8766/admin/simulation/demo?location={location}&risk={risk}'})
                        wait("document.querySelectorAll('tbody tr').length===8 && document.querySelector('.leaflet-container canvas')!==null")
                        assert evaluate("[...document.querySelectorAll('tbody tr')].filter(r=>r.textContent.includes('INSIDE DANGER ZONE')).length") == 4
                        assert evaluate("[...document.querySelectorAll('tbody tr')].filter(r=>r.textContent.includes('OUTSIDE DANGER ZONE')).length") == 4
                        assert evaluate("document.querySelector('textarea').value").find(location) >= 0
                        assert evaluate("document.querySelector('section[aria-label=\"Simulation control\"]').innerText.includes('Simulation estimate')")
                        assert evaluate("[...document.querySelectorAll('.leaflet-tooltip')].some(t=>t.textContent.includes('SAFE AREA'))")
                        scenario = build_scenario(location,risk)
                        assert scenario['route']['safe_zone']['name'] in evaluate("document.querySelector('section[aria-label=\"Simulation control\"]').innerText")
                        wait("[...document.querySelectorAll('img.leaflet-tile')].every(t=>t.complete && t.naturalWidth>0)")
                        image = command('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
                        (output / f'{location}_{risk}_route.png').write_bytes(base64.b64decode(image['data']))
                        evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Generate SMS Excel').click()")
                        wait("document.body.innerText.includes('Excel generated successfully')")
                        for _ in range(50):
                            workbooks = list(output.glob(f'LandSense_{location}_{risk}_SMS_*.xlsx'))
                            if workbooks:
                                break
                            time.sleep(.1)
                        assert workbooks, 'Download missing'
                        workbook = load_workbook(workbooks[0])
                        assert workbook.active.max_row == 5
                        workbook.close()
                        route_info = build_scenario(location, risk)['route']['route']
                        results.append(f"{location} {risk}: {route_info['safe_area_id']}, mapped road route {route_info['distance_meters']} m, boundary clearance {route_info['boundary_distance_meters']} m, screenshot and download verified")
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Edit Message').click()")
                evaluate("Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(document.querySelector('textarea'),'Custom Makutta evacuation drill'); document.querySelector('textarea').dispatchEvent(new Event('input',{bubbles:true}))")
                wait("document.querySelector('textarea').value==='Custom Makutta evacuation drill'")
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Generate Excel').click()")
                wait("document.body.innerText.includes('Excel generated successfully')")
                edited_message = None
                for _ in range(50):
                    for path in output.glob('LandSense_Makutta_CRITICAL_SMS_*.xlsx'):
                        try:
                            edited_book = load_workbook(path)
                            edited_message = edited_book.active['C2'].value
                            edited_book.close()
                        except Exception:
                            continue
                    if edited_message == 'SIMULATION ONLY — Custom Makutta evacuation drill':
                        break
                    time.sleep(.1)
                assert edited_message == 'SIMULATION ONLY — Custom Makutta evacuation drill', 'Edited message download missing'
                command('Emulation.setDeviceMetricsOverride', {'width': 768, 'height': 1024, 'deviceScaleFactor': 1, 'mobile': False})
                assert evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Tablet horizontal overflow'
                command('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
                time.sleep(.4)
                image = command('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True})
                (output / 'simulation-dashboard.png').write_bytes(base64.b64decode(image['data']))
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Reset Simulation').click()")
                wait("document.querySelectorAll('tbody tr').length===0")
                assert evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Generate SMS Excel').disabled")
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Recalculate Danger Zone').click()")
                wait("document.querySelectorAll('tbody tr').length===8")
                evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Calculate Safe Route').click()")
                wait("document.body.innerText.includes('Route calculated by LandSense — deterministic demonstration path')")
                runtime_errors = [e for e in events if e.get('method') == 'Runtime.exceptionThrown']
                assert not runtime_errors, runtime_errors
                console_errors = [e for e in events if e.get('method') == 'Runtime.consoleAPICalled' and e['params'].get('type') == 'error']
                assert not console_errors, console_errors
                assert all(path == '/admin/simulation/visual/excel' for method, path in requests if method == 'POST'), requests
                assert sum(path == '/admin/simulation/visual/scenario' for method, path in requests) == scenario_requests_before
                results.extend(['Admin selection carried to demo: Makutta CRITICAL', 'Message editing, reset, recalculation and safe-route controls: verified', 'Tablet: no horizontal overflow', 'Runtime exceptions: 0', 'Mutation requests: fictional Excel generation only'])
                (output / 'browser-results.txt').write_text('\n'.join(results), encoding='utf-8')
                print('\n'.join(results))
                command('Browser.close')
            browser.wait(timeout=10)
            browser = None
    finally:
        if browser is not None:
            browser.terminate()
            browser.wait(timeout=10)
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == '__main__':
    main()
