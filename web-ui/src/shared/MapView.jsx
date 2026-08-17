import { useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'

const RISK_STYLES = {
  SAFE: { fill: '#22c55e', stroke: '#34d399', heat: 'rgba(34,197,94,0.18)' },
  MEDIUM: { fill: '#f59e0b', stroke: '#fbbf24', heat: 'rgba(245,158,11,0.22)' },
  WARNING: { fill: '#f59e0b', stroke: '#fbbf24', heat: 'rgba(245,158,11,0.22)' },
  HIGH: { fill: '#ef4444', stroke: '#fb7185', heat: 'rgba(239,68,68,0.26)' },
  CRITICAL: { fill: '#dc2626', stroke: '#f87171', heat: 'rgba(220,38,38,0.30)' }
}

function getCenterFromFeature(feature) {
  const coords = feature?.geometry?.coordinates?.[0] || []
  if (!coords.length) return null
  const sum = coords.reduce((acc, pair) => {
    acc.lat += pair[1]
    acc.lng += pair[0]
    return acc
  }, { lat: 0, lng: 0 })
  return coords.length ? [sum.lat / coords.length, sum.lng / coords.length] : null
}

function getFeatureStyle(feature, defaultStyle){
  const riskLevel = String(feature?.properties?.risk_level || 'SAFE').toUpperCase()
  const style = RISK_STYLES[riskLevel] || defaultStyle
  return {
    color: style.stroke,
    weight: 2,
    opacity: 0.9,
    fillColor: style.fill,
    fillOpacity: 0.16
  }
}

function renderUserLocationLayer(L, map, userLocation, locationStatus) {
  const latitude = Number(userLocation?.lat)
  const longitude = Number(userLocation?.lng)
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null

  const rawAccuracy = userLocation?.accuracy
  const accuracy = Number(rawAccuracy)
  const hasAccuracy = rawAccuracy != null && Number.isFinite(accuracy) && accuracy >= 0
  const layer = L.layerGroup().addTo(map)
  if (hasAccuracy) {
    L.circle([latitude, longitude], {
      radius: Math.max(accuracy, 1),
      color: '#38bdf8',
      weight: 1,
      opacity: 0.65,
      fillColor: '#38bdf8',
      fillOpacity: 0.10
    }).addTo(layer)
  }

  const marker = L.circleMarker([latitude, longitude], {
    radius: 9,
    color: '#ffffff',
    weight: 3,
    fillColor: '#0ea5e9',
    fillOpacity: 1
  }).addTo(layer)
  marker.bindTooltip('🔵 YOU ARE HERE', { permanent: true, direction: 'top', opacity: 0.95 })
  marker.bindPopup([
    '<b>Your Location</b>',
    `Latitude: ${latitude.toFixed(6)}`,
    `Longitude: ${longitude.toFixed(6)}`,
    hasAccuracy ? `Accuracy: ${Math.round(accuracy)} m` : 'Accuracy: unavailable',
    locationStatus ? `Status: ${locationStatus}` : ''
  ].filter(Boolean).join('<br>'))
  marker.bringToFront()
  return layer
}

export default function MapView({ zones = [], userLocation = null, userLocationStatus = '', simulatedLocation = null, simulatedCitizens = [], incidentLocation = null, incidentRadiusMeters = 0, route = null, risk = 'SAFE', simulation = false, selectedZone = null, selectedZoneRisk = '', selectedZoneDuration = null, recipientLocations = [], landslideRecords = [] }){
  const ref = useRef()
  const hasCenteredOnUserRef = useRef(false)
  const viewportRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const leafletRef = useRef(null)
  const userLocationLayerRef = useRef(null)
  const latestUserLocationRef = useRef(userLocation)
  const latestUserLocationStatusRef = useRef(userLocationStatus)

  // Leaflet loads asynchronously. Keep the initializer pointed at the latest
  // GPS fix without making each GPS update recreate the whole map.
  latestUserLocationRef.current = userLocation
  latestUserLocationStatusRef.current = userLocationStatus
  const hasValidUserLocation = Number.isFinite(Number(userLocation?.lat)) && Number.isFinite(Number(userLocation?.lng))

  useEffect(()=>{
    let L
    let map
    let overlays = []
    let cancelled = false
    
    async function init(){
      L = (await import('leaflet')).default
      if(cancelled || !ref.current) return
      
      const savedViewport = viewportRef.current
      map = L.map(ref.current, { zoomControl: true, attributionControl: false, preferCanvas: true }).setView(
        savedViewport ? [savedViewport.latitude, savedViewport.longitude] : [14.5, 76.2],
        savedViewport?.zoom ?? 6
      )
      mapInstanceRef.current = map
      leafletRef.current = L
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map)

      const currentRiskStyle = RISK_STYLES[risk] || RISK_STYLES.SAFE

      const geoLayer = L.geoJSON({
        type: 'FeatureCollection',
        // Incident demos use their circular radius only. Configured polygons remain
        // available in the configured-zone workflow, but must not look like incident geometry.
        features: incidentLocation ? [] : zones
      }, {
        style: (feature) => getFeatureStyle(feature, currentRiskStyle),
        onEachFeature: (feature, layer) => {
          const name = feature?.properties?.name || 'Risk zone'
          const level = feature?.properties?.risk_level || 'SAFE'
          const status = feature?.properties?.status
          layer.bindTooltip(`${name} • ${level}`, { sticky: true, direction: 'top', opacity: 0.95 })
          layer.bindPopup([
            '<b>LandSense Risk Zone</b>',
            `Name: ${name}`,
            `Risk Level: ${level}`,
            status ? `Status: ${status}` : ''
          ].filter(Boolean).join('<br>'))
        }
      }).addTo(map)
      overlays.push(geoLayer)

      const inventoryLayer = L.layerGroup().addTo(map)
      landslideRecords.forEach((record) => {
        const latitude = Number(record?.latitude)
        const longitude = Number(record?.longitude)
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
        const marker = L.circleMarker([latitude, longitude], {
          radius: 3,
          color: '#c4b5fd',
          weight: 1,
          fillColor: '#8b5cf6',
          fillOpacity: 0.72
        }).addTo(inventoryLayer)
        const location = [record?.district, record?.state].filter(Boolean).join(', ')
        const year = record?.initiation_year ? ` • ${record.initiation_year}` : ''
        marker.bindTooltip(`Dataset-backed landslide inventory${location ? ` • ${location}` : ''}${year}`, {
          sticky: true,
          direction: 'top',
          opacity: 0.95
        })
      })
      const inventoryControl = L.control.layers(null, {
        'Dataset-backed landslide inventory': inventoryLayer
      }, { collapsed: true }).addTo(map)
      overlays.push(inventoryLayer, inventoryControl)

      zones.forEach((feature) => {
        const center = getCenterFromFeature(feature)
        if (!center) return
        const riskLevel = String(feature?.properties?.risk_level || 'SAFE').toUpperCase()
        const style = RISK_STYLES[riskLevel] || currentRiskStyle
        overlays.push(L.circle(center, {
          radius: riskLevel === 'HIGH' || riskLevel === 'CRITICAL' ? 12000 : 8000,
          color: style.stroke,
          weight: 1,
          fillColor: style.fill,
          fillOpacity: 0.10,
          className: 'landsense-pulse'
        }).addTo(map))
      })

      if (selectedZone?.geometry) {
        const selectedLayer = L.geoJSON(selectedZone, {
          style: {
            color: '#22d3ee',
            weight: 4,
            opacity: 1,
            fillColor: '#22d3ee',
            fillOpacity: 0.08,
            dashArray: '8 6'
          }
        }).bindTooltip(`CONFIGURED RISK ZONE: ${selectedZone?.properties?.name || 'Configured zone'} · ${selectedZoneRisk || selectedZone?.properties?.risk_level || 'Risk unavailable'}`, { sticky: true })
        selectedLayer.bindPopup([
          '<b>Configured Risk Zone</b>',
          `Name: ${selectedZone?.properties?.name || 'Configured zone'}`,
          `Risk: ${selectedZoneRisk || selectedZone?.properties?.risk_level || 'Unavailable'}`,
          selectedZone?.properties?.status ? `Status: ${selectedZone.properties.status}` : '',
          selectedZoneDuration != null ? `Duration: ${selectedZoneDuration} minutes` : ''
        ].filter(Boolean).join('<br>'))
        selectedLayer.addTo(map)
        overlays.push(selectedLayer)
        const selectedBounds = selectedLayer.getBounds()
        if (selectedBounds.isValid()) {
          map.fitBounds(selectedBounds, { padding: [36, 36], maxZoom: 12, animate: true })
        }
      }

      recipientLocations.forEach((recipient) => {
        const latitude = Number(recipient?.latitude)
        const longitude = Number(recipient?.longitude)
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
        const marker = L.circleMarker([latitude, longitude], {
          radius: 7,
          color: '#ffffff',
          weight: 2,
          fillColor: '#38bdf8',
          fillOpacity: 1
        }).addTo(map)
        marker.bindTooltip(`Recipient preview: ${recipient?.phone_masked || recipient?.user_id || 'Registered user'}`, { direction: 'top', opacity: 0.95 })
        overlays.push(marker)
      })

      const currentUserLocation = latestUserLocationRef.current
      userLocationLayerRef.current = renderUserLocationLayer(
        L,
        map,
        currentUserLocation,
        latestUserLocationStatusRef.current
      )

      if (simulatedLocation?.lat && simulatedLocation?.lng) {
        const marker = L.circleMarker([simulatedLocation.lat, simulatedLocation.lng], {
          radius: 9,
          color: '#ffffff',
          weight: 2,
          fillColor: '#f97316',
          fillOpacity: 1
        }).addTo(map)
        marker.bindTooltip(simulatedLocation.label || 'Simulated citizen', { permanent: false, direction: 'top', opacity: 0.95 })
        overlays.push(marker)
      }

      simulatedCitizens.forEach((citizen) => {
        const latitude = Number(citizen?.latitude)
        const longitude = Number(citizen?.longitude)
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
        const marker = L.circleMarker([latitude, longitude], {
          radius: 7, color: '#ffffff', weight: 2, fillColor: '#f97316', fillOpacity: citizen.inside === false ? 0.55 : 1
        }).addTo(map)
        marker.bindTooltip(`SIMULATED CITIZEN${citizen.inside === false ? ' — outside affected area' : ''}`, { direction: 'top', opacity: 0.95 })
        overlays.push(marker)
      })

      if (incidentLocation?.lat && incidentLocation?.lng) {
        const incidentColor = String(incidentLocation.risk || risk).toUpperCase() === 'CRITICAL' ? '#dc2626' : '#f97316'
        const affectedArea = L.circle([incidentLocation.lat, incidentLocation.lng], {
          radius: Number(incidentRadiusMeters) || 1000,
          color: incidentColor,
          weight: 3,
          fillColor: incidentColor,
          fillOpacity: 0.16,
          dashArray: '8 6'
        }).addTo(map)
        affectedArea.bindTooltip('DEMO INCIDENT — affected area', { sticky: true, opacity: 0.95 })
        overlays.push(affectedArea)

        const marker = L.circleMarker([incidentLocation.lat, incidentLocation.lng], {
          radius: 12, color: '#ffffff', weight: 3, fillColor: incidentColor, fillOpacity: 1
        }).addTo(map)
        marker.bindTooltip(`🚨 SIMULATED INCIDENT<br>${incidentLocation.title || 'Incident location'}<br>${incidentLocation.location || ''}<br>${incidentLocation.date || ''}`, { permanent: true, direction: 'top', opacity: 0.95 })
        marker.bindPopup([
          '<b>SIMULATED INCIDENT</b>',
          incidentLocation.title || 'Incident location',
          `Risk: ${String(incidentLocation.risk || risk).toUpperCase()}`,
          `Status: ${incidentLocation.status || 'Active simulation'}`,
          `Latitude: ${Number(incidentLocation.lat).toFixed(6)}`,
          `Longitude: ${Number(incidentLocation.lng).toFixed(6)}`
        ].join('<br>'))
        overlays.push(marker)
        map.setView([incidentLocation.lat, incidentLocation.lng], Number(incidentLocation.zoom) || 13, { animate: true })
      }

      if (route?.start && route?.end) {
        const routePath = Array.isArray(route.path) && route.path.length >= 2
          ? route.path
          : [route.start, route.end]
        overlays.push(L.polyline(routePath, {
          color: '#7dd3fc',
          weight: 4,
          opacity: 0.9,
          dashArray: '10 12'
        }).addTo(map))
        overlays.push(L.marker(route.end, {
          icon: L.divIcon({
            className: 'landsense-safezone',
            html: '<div class="safezone-dot"></div>',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
          })
        }).bindTooltip('Safer area', { permanent: false, direction: 'top', opacity: 0.95 }).addTo(map))
      }

      if (incidentLocation?.lat && incidentLocation?.lng) {
        // The incident controls only the viewport; the independent real-user marker remains rendered.
      } else if (selectedZone?.geometry) {
        // The selected configured-zone layer already fitted its actual geometry above.
      } else if (Number.isFinite(Number(currentUserLocation?.lat)) && Number.isFinite(Number(currentUserLocation?.lng))) {
        if (!hasCenteredOnUserRef.current) {
          map.setView([currentUserLocation.lat, currentUserLocation.lng], 15, { animate: true })
          hasCenteredOnUserRef.current = true
        }
      } else if (!savedViewport && zones.length) {
        const first = getCenterFromFeature(zones[0])
        if (first) map.setView(first, 7, { animate: true })
      }
    }
    
    init()
    return ()=>{
      cancelled = true
      if (map) {
        const center = map.getCenter()
        viewportRef.current = { latitude: center.lat, longitude: center.lng, zoom: map.getZoom() }
        map.remove()
      }
      mapInstanceRef.current = null
      leafletRef.current = null
      userLocationLayerRef.current = null
      overlays.forEach((layer) => layer?.remove?.())
    }
  }, [zones, simulatedLocation, simulatedCitizens, incidentLocation, incidentRadiusMeters, route, risk, simulation, selectedZone, selectedZoneRisk, selectedZoneDuration, recipientLocations, landslideRecords])

  useEffect(() => {
    const map = mapInstanceRef.current
    const L = leafletRef.current
    if (!map || !L) return

    userLocationLayerRef.current?.remove?.()
    userLocationLayerRef.current = renderUserLocationLayer(L, map, userLocation, userLocationStatus)

    const latitude = Number(userLocation?.lat)
    const longitude = Number(userLocation?.lng)
    if (!hasCenteredOnUserRef.current && Number.isFinite(latitude) && Number.isFinite(longitude)) {
      map.setView([latitude, longitude], 15, { animate: true })
      hasCenteredOnUserRef.current = true
    }
  }, [userLocation, userLocationStatus])

  return <div className="relative h-full w-full"><div ref={ref} className="h-full w-full" aria-label={simulation ? 'Map showing real, simulated citizen, and incident locations separately' : 'Map showing configured risk zones and historical landslide inventory'} /><div className="pointer-events-none absolute bottom-3 left-3 z-[500] space-y-1 rounded-lg border border-white/20 bg-slate-950/85 px-3 py-2 text-[10px] text-slate-100 shadow-lg">{landslideRecords.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-violet-500" />Historical landslide inventory</div> : null}{zones.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-rose-500" />Configured risk zone</div> : null}{hasValidUserLocation ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-sky-500" />Real user location</div> : null}{simulatedLocation || simulatedCitizens.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-orange-500" />Simulated location</div> : null}{incidentLocation ? <><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-red-600" />Simulated incident</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full border border-red-400 bg-red-600/30" />Affected incident area</div></> : null}{recipientLocations.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-sky-400" />Real recipient preview</div> : null}{selectedZone ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-cyan-400" />Selected configured zone</div> : null}</div>{simulation ? <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-lg border border-amber-200/40 bg-amber-500/90 px-2.5 py-1 text-xs font-bold tracking-wide text-slate-950 shadow-lg">SIMULATION</div> : null}</div>
}
