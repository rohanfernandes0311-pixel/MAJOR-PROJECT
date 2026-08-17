# Location-Based Landslide Alert System using Geo-Fencing and Machine Learning

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

## Secure Auth + Alert APIs

(Removed) Interactive login flows and related endpoints.

## Auth + Security Environment Variables

```bash
set JWT_SECRET=replace_with_long_random_secret
set JWT_ALGO=HS256
set ACCESS_TOKEN_TTL_MIN=15
set REFRESH_TOKEN_TTL_DAYS=7
set PHONE_HASH_SALT=replace_with_random_salt
set RECAPTCHA_SECRET_KEY=your_recaptcha_secret
set ENFORCE_HTTPS=true
set ALLOW_INSECURE_LOCALHOST=true

set TWILIO_ACCOUNT_SID=...
set TWILIO_AUTH_TOKEN=...
set TWILIO_SMS_FROM=+1XXXXXXXXXX
```

Notes:

 - Alert SMS messages are sent when Twilio is configured; otherwise they are simulated and logged.

See secure architecture and schema details in:

- (Removed) Secure-auth architecture document.

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
