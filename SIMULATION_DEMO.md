# Admin emergency demonstration

In Admin → Kodagu Emergency Simulation, select one of the five locations and HIGH or CRITICAL, then open **Open Simulation Demonstration**. The existing route `/admin/simulation/demo` carries both selections. Creating a synthetic zone and confirming its alert preview are local demonstration actions. Other Admin tools and the citizen workflow remain separate.

The page displays eight fictional registered people. The existing Python point-in-polygon implementation checks their coordinates: four are inside and eligible; four are outside and excluded. The demo map reuses `MapView` and Leaflet. Red represents the synthetic danger polygon, gray represents excluded people, cyan outlines eligible people, and green represents the route and safe assembly polygon.

Each location has explicit independent centers, HIGH/CRITICAL danger polygons, eight user coordinates and three assembly candidates in `web-ui/src/data/simulationConfig.json`, shared by the browser and Excel backend. The map constructs its scenario locally and never waits for a simulation API response. Both `/admin/simulation` and `/admin/simulation/demo` open the same admin-protected page. Hazard footprints and assembly sites are fictional demonstration data; the assembly sites are not verified shelters.

Road corridors use cached OpenStreetMap road-node geometry for each location. `scripts/fetch_simulation_roads.py` prepares the source snapshots in `validation/simulation/*-osm.xml` and `osm-roads-source.json`. `scripts/prepare_location_simulations.py` builds a road graph, finds routes from the affected-user centroid's nearby road node, and rejects paths that re-enter the danger zone after exiting. The rural synthetic center anchors were moved onto nearby mapped road points. Short connectors join the user centroid to the road; remaining waypoints follow mapped roads. The configuration retains source way/node IDs and road names for inspection. Source: [OpenStreetMap API](https://api.openstreetmap.org/api/0.6/map), [ODbL and attribution](https://www.openstreetmap.org/copyright). Snapshot retrieval date: 2026-10-04. No routing network call or Shapely dependency is required at runtime; Shapely is used only by the preparation script.

At runtime, both browser and Python evaluate all three local assembly candidates against the selected polygon. They reject overlapping sites, sites outside the 300-1000 m boundary-clearance range, and routes that re-enter danger after exiting. The nearest valid candidate is chosen by total Haversine route distance, including the user-cluster connector. The actual boundary intersection is inserted into the road path and returned with its exit index. HIGH and CRITICAL use their own polygons and road corridors; the enlarged CRITICAL zone makes each HIGH destination too close, so another local site is selected. Selected total distances are approximately 826-1724 m, with boundary clearances of 309-399 m. Walking estimates use 75 m/min. Map bounds focus on the danger polygon, affected users, route and safe area; distant excluded people remain available by panning or zooming out.

The new `/admin/simulation/visual/scenario` and `/admin/simulation/visual/excel` endpoints require Admin authentication. They do not read registered users, use the production database, change shared simulation state, create alerts, or call SMS/FCM transports. Recipient eligibility is recomputed on export; the browser cannot provide recipient phone numbers or containment flags.

Set `HTTPSMS_FROM_NUMBER` to the application's configured E.164 sender before generating Excel. The export reuses `services/httpsms_export.py` and has exactly these headers:

`FromPhoneNumber`, `ToPhoneNumber`, `Content`, `SendTime(optional)`

The workbook has only four affected demo recipients; send times are blank. Recipient numbers `+910000000001` through `+910000000008` are intentionally non-dialable placeholders, not real user phone numbers. These files demonstrate the httpSMS template and must not be used for live dispatch. Exported messages always include `SIMULATION ONLY`. The filename uses the date in Asia/Kolkata.

No uploaded `.xlsx` attachment was available in this session. The existing workbook generator was retained with the four exact column names supplied in the request.

## Verification

From `files (2)`:

```powershell
python -m unittest tests.test_simulation_demonstration -v
```

From `files (2)/web-ui`:

```powershell
npm run build
npm test
```

On Windows, after building, `python scripts/verify_simulation_browser.py` runs the built application in hidden headless Edge using a loopback fixture server. It requires `websockets`, opens no production database, and stops after checking Admin navigation, all ten scenarios, message editing, downloads, reset, safe-route controls and tablet sizing. The authentication override exists only in the test fixture. Workbooks, separate map screenshots for all ten location/risk combinations and browser results are saved to `validation/simulation`.
