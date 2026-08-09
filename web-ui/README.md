LandSense - Web UI

This folder contains the production React + Vite frontend used by the backend at runtime.

Key notes:
- Public UI includes migrated legacy workflows: monitoring start/stop loop, live GPS updates, geofence map overlays, safe route planning, realtime risk checks, local notifications, voice guidance, and offline-aware status handling.
- Admin dashboard includes backend event analytics and risk/rainfall visualizations.
- PWA support is implemented via `public/manifest.json` and `public/sw.js`.

Quick start (requires Node.js >=18):

```bash
cd "files (2)/web-ui"
npm install
npm run dev
```

Build for production:

```bash
npm run build
npm run preview
```

Production entry points:
- `src/pages/Public.jsx`
- `src/pages/Admin.jsx`
- `public/sw.js`
- `public/manifest.json`

Build output:
- `dist/` (served by FastAPI from the project root)
