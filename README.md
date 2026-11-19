# Location-Based Landslide Alert System using Geo-Fencing and Machine Learning

## Current setup and operations

LANDsense is a monitoring aid. It is not an official emergency-alert service. Simulation messages and exports are demonstration material only; they must not be treated as real warnings or dispatched as live alerts.

### Requirements and setup

- Python 3.11 or later and Node.js/npm.
- A PostgreSQL/Neon database URL for backend persistence. Use a Neon branch for development and migration checks.
- Optional provider credentials as documented in `.env.example`; never put private credentials in a `VITE_` variable.

From the repository root, create and activate a virtual environment, then install the backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt pytest
Copy-Item .env.example .env
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. Edit `.env` with a Neon branch `DATABASE_URL`, a private `JWT_SECRET` of at least 32 bytes, and any optional provider settings you need. Never commit `.env` or service-account credentials. `config/firebase-service-account.json` is read by the backend Firebase Admin SDK and must remain private.

The root `.env.example` documents backend settings and all discovered frontend build variables. Copy `web-ui/.env.example` to `web-ui/.env` for Vite; Firebase `VITE_` values are browser-visible configuration, not secrets. `CORS_ALLOWED_ORIGINS` accepts explicit comma-separated origins. The development defaults are `http://localhost:5173` and `http://127.0.0.1:5173`; configure the deployed frontend's exact HTTPS origin in production.

Backend configuration includes `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGO`, `ENVIRONMENT`/`APP_ENV`, token and OTP limits, `CORS_ALLOWED_ORIGINS`, and optional SMS, weather, Earthdata, mesh, extraction, and Copernicus settings. Frontend configuration includes `VITE_API_BASE_URL`, the six `VITE_FIREBASE_*` client settings, `VITE_COMMUNITY_REPORTS_ENHANCED`, and `VITE_SIMULATION_MESSAGE_LANGUAGE`. Each variable has a placeholder and comment in the relevant example file. `import.meta.env.DEV` is a Vite-provided build constant, not a user-configured variable.

For production, set `CORS_ALLOWED_ORIGINS` to the exact comma-separated HTTPS origin(s) serving the frontend, for example `https://app.example.org`. Do not use `*`; backend startup rejects wildcard configuration. CORS permits the app's `GET`, `POST`, and `OPTIONS` methods and `Authorization`/`Content-Type` headers. The frontend uses bearer authorization for authenticated resource requests; `/auth/refresh` sends its refresh token in a JSON body. The app does not use cookies for API authentication.

### Run the application

Start the backend from the repository root:

```powershell
uvicorn backend_api:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal, install and start the frontend:

```powershell
cd web-ui
npm install
npm run dev
```

The Vite development proxy targets `http://127.0.0.1:8000` unless `VITE_API_BASE_URL` overrides it. To create a production frontend bundle, run `npm run build` in `web-ui`.

### Database migration

Create a disposable Neon branch and point `DATABASE_URL` to that branch before migrating. From the repository root with the virtual environment active, run:

```powershell
python -m database.migrate_add_community_reports
```

This creates the additive community-report tables/columns. Verify it on the branch before applying it to any other environment. Do not use a production URL for routine migration checks.

### Tests

From the repository root:

```powershell
python -m pytest -q
```

From `web-ui`:

```powershell
npm test
```

The backend tests use isolated fixtures/mocks where provided. Do not point tests at production data.

### Roles and feature flags

- **Citizen** accounts use the citizen monitoring and community-report flows.
- **Admin** accounts can access administrative review, simulation, and operational tools; backend routes enforce administrator authorization.
- Unauthenticated visitors can access only the routes explicitly designated public.
- `VITE_COMMUNITY_REPORTS_ENHANCED=false` restores the earlier community-report form and map behavior.
- `VITE_SIMULATION_MESSAGE_LANGUAGE=false` disables Kannada/bilingual simulation message templates. Simulation output remains demonstration-only.

The FastAPI backend owns authentication, report review, persistence, provider integrations, and administrative APIs. The React/Vite frontend provides citizen/admin screens, maps, and PWA assets. PostgreSQL/Neon is the runtime database; SQLite files are migration or test artifacts.

### Downloading terrain tiles

The SRTM tile URLs and expected SHA-256 digests are listed in `data/research/south_india_environmental_features/terrain_manifest.json`. Install backend requirements, then run:

```powershell
python scripts/download_srtm_tiles.py
```

The script downloads only manifest-listed HTTPS tiles, verifies each digest, and atomically replaces a tile only after verification. Correctly verified local tiles are skipped. The compressed `.hgt.gz` files are local research inputs and are ignored by Git; keep the small manifest and derived, reviewable data under version control as appropriate.

End-to-end lightweight major-project prototype for Indian regions.

This repository now supports both:

1. ML core workflow (dataset, preprocessing, RF/XGBoost training, prediction, alerts, Streamlit dashboard)
2. Real-time location-based warning workflow (FastAPI backend, geofencing polygons, Leaflet map, live rainfall, voice and SMS fallback, evacuation route planning)

## Key Features

- Geo-fencing using latitude-longitude polygons (GeoJSON)
- Real-time risk prediction (LOW / MEDIUM / HIGH)
- Live rainfall integration (OpenWeatherMap + simulation fallback)
- Interactive Leaflet map with danger zones and user location
- Voice warning via Web Speech API
- Offline SMS fallback simulation and Twilio SMS support
- Dijkstra-based safe route suggestion avoiding high-risk zones
- SQLite event logging

## Project Structure

- app.py: Streamlit dashboard (ML + analytics)
- generate_dataset.py: Indian CSV ingestion + synthetic fallback + normalized export
- train_models.py: RF + XGBoost training and evaluation
- predict.py: prediction functions for single/batch inference
- alert_system.py: threshold alerting + Telegram + WhatsApp (Twilio)
- insar_processing.py: simulated Sentinel-1/InSAR extension
- advanced_extension.py: optional future-scope LSTM utilities
- backend_api.py: FastAPI backend for geofence tracking and live alerts
- geofencing.py: polygon zone engine with entry/exit detection
- rainfall_service.py: weather API integration and fallback simulation
- sms_service.py: online/offline SMS handling
- route_planner.py: Dijkstra evacuation route logic
- config/risk_zones.geojson: sample landslide-prone polygons
- web-ui/: production React + Vite frontend (public safety UI + admin analytics)
- web-ui/src/pages/Public.jsx: live map UI + monitoring workflow + alerts + voice guidance
- web-ui/src/pages/Admin.jsx: analytics dashboard powered by backend events
- docs/architecture.md: architecture explanation and diagram text
- docs/architecture_drawio.xml: importable draw.io architecture file
- docs/ieee_report.md: IEEE-style report sections for viva/demo
- docs/ML_DATASET_QUALITY_AUDIT.md: verified dataset provenance and quality audit
- docs/GROUND_TRUTH_DATA_CONTRACT.md: schema and labeling contract for future real observations
- docs/ML_DATA_SOURCE_DISCOVERY.md: authoritative landslide and environmental data-source plan
- docs/SOUTH_INDIAN_DATA_ACQUISITION_REPORT.md: provenance-preserving Kodagu and Kerala research-data acquisition

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional environment variables:

```bash
set OPENWEATHER_API_KEY=your_openweather_key
set TWILIO_ACCOUNT_SID=your_twilio_sid
set TWILIO_AUTH_TOKEN=your_twilio_token
set TWILIO_SMS_FROM=+1XXXXXXXXXX
set TELEGRAM_BOT_TOKEN=your_telegram_bot_token
set TELEGRAM_CHAT_ID=your_telegram_chat_id
set TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
set TWILIO_WHATSAPP_TO=whatsapp:+91XXXXXXXXXX
```

## Phase 1 Execution (Mandatory)

1. Generate dataset:

```bash
python generate_dataset.py
```

or with real Indian CSV files:

```bash
python generate_dataset.py --raigad-csv path/to/raigad.csv --rainfall-csv path/to/rainfall.csv --soil-csv path/to/soil.csv
```

2. Train models:

```bash
python train_models.py
```

For a non-destructive reliability audit (including balanced and macro metrics,
per-class results, stratified cross-validation, duplicate checks, and label
provenance), run:

```bash
python train_models.py --audit-only
```

This writes `models/audit_metrics.json` and does not replace the production
model artifacts.

3. Test prediction engine:

```bash
python predict.py
```

4. Run Streamlit analytics dashboard:

```bash
streamlit run app.py
```

## Geo-Fencing + Real-Time System Execution

1. Start backend API:

```bash
python backend_api.py
```

2. Open web map:

http://127.0.0.1:8000/

The backend serves the production frontend at `/` and keeps `/frontend` compatibility redirects for legacy links.

3. In the map UI:

- Send live/manual location updates
- Watch risk level and geofence event changes
- Trigger voice warning on HIGH risk
- Generate safe evacuation route

## API Quick Reference

- GET /health
- GET /zones
- GET /events
- POST /predict-risk
- POST /location-update
- POST /route-safe

## Disaster Simulation Mode (Enterprise-Safe)

The platform includes an isolated Demo / Emergency Simulation Mode designed for controlled demonstrations and drills.

Design goals:

- No disruption to live monitoring workflows
- No changes to core prediction/geofence engine contracts
- Simulation state isolated from live state
- Reuse of existing emergency alert UI and pipeline
- Safe rollback by disabling simulation mode

### Security

- Simulation state is available only to users whose signed JWT has the `Admin` role.
- There is no separate simulation key or session mechanism.
- External notifications are always suppressed while simulation is enabled.

### Simulation API Contract

Every simulation endpoint requires `Authorization: Bearer <admin access token>`.

Endpoints:

- `GET /admin/simulation/state`
	- Returns current simulation status.
- `POST /admin/simulation/state`
	- Enables/disables simulation mode.
	- Request body:

```json
{
	"enabled": true,
	"forced_risk": "HIGH",
	"escalation_enabled": false,
	"scenario_name": "High Risk"
}
```

- `GET /admin/simulation/events?limit=100`
	- Returns simulation-only event history.

Behavior when enabled:

- Simulates a configured risk-zone context
- Uses the selected risk (`LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`)
- Triggers existing emergency alert rendering/voice flows
- Keeps simulation events separate from live event analytics storage
- Never creates live alerts or queues SMS notifications

### Demo Drill Runbook

1. Start backend:

```bash
python backend_api.py
```

2. Sign in as an Admin and open the admin dashboard (`/admin`), then enable a scenario.
3. Open public dashboard (`/`) and start monitoring.
4. Verify emergency state:
	- `⚠ SIMULATION MODE ACTIVE` banner visible
	 - High-risk emergency status shown
	 - Evacuation guidance and alarm UI available
5. Turn off internet/WiFi.
6. Refresh the public dashboard.
7. Verify offline emergency restoration:
	 - Persisted warning remains visible from browser storage
	 - Offline restore indicator appears
8. Disable simulation in admin dashboard.
9. Verify cleanup:
	 - Live mode restored
	 - Simulated persisted emergency snapshot cleared safely

### Offline Emergency Persistence (Frontend)

Browser-local emergency persistence is implemented via a dedicated utility module and integrated around the existing public emergency UI workflow:

- Persist on emergency state (HIGH/WARNING/simulation)
- Restore on offline refresh or temporary backend failure
- Clear on danger end or simulation disable
- Optional manual dismiss in UI

This keeps emergency visibility resilient during connectivity loss without changing backend APIs.

## Auth and alert APIs

Interactive auth, OTP, session, and alert APIs are implemented in the backend. See the current setup section above for role behavior and the complete environment-variable examples. Keep all provider credentials server-side; never use a `VITE_` prefix for a private value.

## Sample Alert Message

"⚠️ Landslide Warning: You have entered a high-risk zone. Move to a safer location immediately."

## IEEE/Viva Report Material

See:

- docs/ieee_report.md
- docs/architecture.md
- docs/architecture_drawio.xml

## Notes

- Designed to stay lightweight and understandable.
- Real-world deployment needs richer ground-truth data, calibrated geofences, and road-network routing.
# Admin httpSMS Excel export

This feature uses existing PostgreSQL users, alert preferences, and saved `locations`
coordinates. Saved coordinates persist while users are offline; subsequent normal
location updates replace them as before. Users without a saved location are not
included. No new registration system or database migration is required.

1. Install backend dependencies: `python -m pip install -r requirements.txt`.
2. Set `HTTPSMS_FROM_NUMBER` in `files (2)/.env` to your httpSMS Android sender
   number, including its country code. Restart the backend after configuration.
3. Build the frontend with `npm ci` then `npm run build` in `web-ui`, and start
   LandSense using the existing startup instructions below.
4. Log in as admin and enable Simulation Mode.
5. Select a configured HIGH or CRITICAL danger zone using the existing zone
   selector or map. Selecting its polygon prepares the export preview; live
   alert activation is not required. Existing synthetic citizen markers and
   catalog incident demos are separate from this configured-zone export.
6. Review **Eligible Users** and explicitly check the intended recipients.
   **Selected Recipients** starts at zero. Being inside the zone does not select
   a user. Review the message before downloading.
7. Click **Download httpSMS Excel** explicitly.
8. Manually upload the downloaded workbook to httpSMS. httpSMS sends the SMS
   through your configured Android phone and SIM. LandSense does not send SMS
   from this feature and does not require an httpSMS API key.

The workbook contains exactly `FromPhoneNumber`, `ToPhoneNumber`, `Content`, and
`SendTime(optional)` with one row per unique, valid, opted-in phone number that
is both inside the selected polygon and explicitly selected by the Admin.
Omitted or empty selections never export the entire eligible population.
Indian mobile numbers with 10 digits or a `91` prefix are normalized to `+91`;
whitespace is removed. Ambiguous or invalid numbers are excluded and listed by
the dashboard's existing privacy-safe citizen identifiers. Explicit international
numbers receive E.164 syntax validation, which does not verify SIM ownership or
deliverability. No generated workbook is stored on the server.

Admin-only API routes (existing Bearer authentication):

- `GET /admin/affected-zones/{zone_id}/httpsms-preview?recipient_ids={selected_display_ids}`
- `GET /admin/affected-zones/{zone_id}/httpsms-excel?revision={preview_revision}&recipient_ids={selected_display_ids}`
- `GET /admin/simulation/visual/recipients?location={approved_location}&risk={HIGH_or_CRITICAL}`
- `POST /admin/simulation/visual/registered-excel`

The dedicated Simulation Demonstration page uses the existing approved simulation
polygons with registered users' saved coordinates. It keeps each location/risk's
selection and edited message independent, and exports selected groups in separate
worksheets. The POST body contains `scenarios`, each with `location`, `risk`,
`revision`, `message`, and explicit `recipient_ids` (the preview's display IDs).
The backend recomputes eligibility and rejects outside users or changed previews.
Reset clears local selections, previews, messages, and controls; it never changes
real users, roles, Firebase, or production alerts. Existing fictional map/route
fixtures remain illustrative and are not used as registered recipients.

The Admin Simulation Actor is a purple diamond labeled as simulated, not real GPS.
It uses only the selected location's existing configured center after checking that
the point lies inside the selected simulation polygon. Missing or invalid positions
are reported without generating replacement coordinates. The actor lives in the
temporary demo scenario, moves with location/risk selection, and is removed on reset.
It never enters the registered-user list, saved-location persistence, location-event
history, or Excel recipient selection. The existing demonstration route retains its
original start point; it is not presented as a route calculated from the actor.

The dashboard supplies the preview revision. If recipients or zone/message
information changes, download returns 409 and asks the admin to refresh before
downloading. Missing sender configuration, empty eligible populations, disabled
simulation, and unavailable zones disable the button or return clear errors.

Run export tests from `files (2)` with
`python -m unittest discover -s tests -p test_httpsms_export.py -v`.
Tests use an isolated database and do not send SMS.
