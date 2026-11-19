import { useEffect, useRef, useState } from 'react'
import 'leaflet/dist/leaflet.css'
import { createLifecycleSafeCanvas } from '../services/leafletCanvasLifecycle'

const EMPTY_LAYERS = []

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

function populateCommunityReportLayer(L, layer, reports, showRejected, verifiedOnly = false) {
  layer.clearLayers()
  const colors = { pending: '#eab308', under_review: '#38bdf8', verified: '#22c55e', rejected: '#94a3b8' }
  reports.forEach((report) => {
    const status = String(report?.status || 'pending').toLowerCase()
    if (verifiedOnly && status !== 'verified') return
    if (status === 'rejected' && !showRejected) return
    const latitude = Number(report?.latitude)
    const longitude = Number(report?.longitude)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
    const category = String(report?.category || 'other').replaceAll('_', ' ')
    const marker = verifiedOnly && status === 'verified'
      ? L.marker([latitude, longitude], {
        icon: L.divIcon({
          className: '',
          html: '<span style="display:flex;width:26px;height:26px;align-items:center;justify-content:center;border:2px solid white;border-radius:50%;background:#087f5b;color:white;font-size:15px;font-weight:700;box-shadow:0 1px 5px #334155">✓</span>',
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        }),
      }).addTo(layer)
      : L.circleMarker([latitude, longitude], {
        radius: status === 'verified' ? 7 : 6,
        color: '#ffffff', weight: 2,
        fillColor: colors[status] || colors.pending,
        fillOpacity: 0.92,
      }).addTo(layer)
    marker.bindTooltip(verifiedOnly ? 'Community verified' : `Community report · ${status.replaceAll('_', ' ')}`, { direction: 'top', opacity: 0.95 })
    const popup = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = verifiedOnly ? 'Community verified' : `Community report · ${status.replaceAll('_', ' ')}`
    const detail = document.createElement('div')
    detail.textContent = `${category} · ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`
    popup.append(heading, detail)
    if (verifiedOnly) {
      const time = document.createElement('div')
      const submittedAt = report?.submitted_at ? new Date(report.submitted_at) : null
      time.textContent = `Reported: ${submittedAt && !Number.isNaN(submittedAt.valueOf()) ? submittedAt.toLocaleString() : 'Date unavailable'}`
      const source = document.createElement('div')
      source.textContent = 'Source: Citizen, verified by admin'
      popup.append(time, source)
    }
    marker.bindPopup(popup)
  })
}

export default function MapView({ zones = EMPTY_LAYERS, userLocation = null, userLocationStatus = '', simulatedLocation = null, simulatedCitizens = EMPTY_LAYERS, incidentLocation = null, incidentRadiusMeters = 0, incidentMode = false, syntheticZone = null, simulationRoute = null, showSimulationLayers = false, affectedUserLocations = EMPTY_LAYERS, mapContext = null, route = null, risk = 'SAFE', simulation = false, selectedZone = null, selectedZoneRisk = '', selectedZoneDuration = null, recipientLocations = EMPTY_LAYERS, landslideRecords = EMPTY_LAYERS, communityReports = EMPTY_LAYERS, showRejectedCommunityReports = false, showCommunityVerifiedReports = false, onRiskAreaSelect = null, simulationSafeZone = null, adminSimulationActor = null }){
  const ref = useRef()
  const [mapError, setMapError] = useState('')
  const hasCenteredOnUserRef = useRef(false)
  const viewportRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const leafletRef = useRef(null)
  const communityReportLayerRef = useRef(null)
  const latestCommunityReportsRef = useRef(communityReports)
  const showRejectedReportsRef = useRef(showRejectedCommunityReports)
  const showCommunityVerifiedReportsRef = useRef(showCommunityVerifiedReports)
  const userLocationLayerRef = useRef(null)
  const latestUserLocationRef = useRef(userLocation)
  const latestUserLocationStatusRef = useRef(userLocationStatus)

  // Leaflet loads asynchronously. Keep the initializer pointed at the latest
  // GPS fix without making each GPS update recreate the whole map.
  latestUserLocationRef.current = userLocation
  latestUserLocationStatusRef.current = userLocationStatus
  latestCommunityReportsRef.current = communityReports
  showRejectedReportsRef.current = showRejectedCommunityReports
  showCommunityVerifiedReportsRef.current = showCommunityVerifiedReports
  const hasValidUserLocation = Number.isFinite(Number(userLocation?.lat)) && Number.isFinite(Number(userLocation?.lng))

  useEffect(()=>{
    setMapError('')
    let L
    let map
    let overlays = []
    let cancelled = false
    let resizeObserver
    
    async function init(){
      L = (await import('leaflet')).default
      if(cancelled || !ref.current) return
      
      const savedViewport = viewportRef.current
      map = L.map(ref.current, { zoomControl: true, attributionControl: false, preferCanvas: true, renderer: createLifecycleSafeCanvas(L), zoomAnimation: !simulationSafeZone }).setView(
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
        features: incidentMode ? [] : zones
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
          if (simulation && ['HIGH', 'CRITICAL'].includes(String(level).toUpperCase()) && onRiskAreaSelect) {
            layer.on('click', () => onRiskAreaSelect({ type: 'configured-zone', id: String(feature?.properties?.zone_id || ''), risk: String(level).toUpperCase(), name }))
          }
        }
      }).addTo(map)
      overlays.push(geoLayer)

      const inventoryLayer = L.layerGroup().addTo(map)
      landslideRecords.slice(0, 2000).forEach((record) => {
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

      const communityReportLayer = L.layerGroup().addTo(map)
      communityReportLayerRef.current = communityReportLayer
      populateCommunityReportLayer(L, communityReportLayer, latestCommunityReportsRef.current, showRejectedReportsRef.current, showCommunityVerifiedReportsRef.current)
      const reportControl = L.control.layers(null, {
        [showCommunityVerifiedReportsRef.current ? 'Community verified · separate from official zones' : 'Community reports · separate from official zones']: communityReportLayer,
      }, { collapsed: true }).addTo(map)
      overlays.push(communityReportLayer, reportControl)

      if (!incidentMode) zones.forEach((feature) => {
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
          selectedZoneDuration != null ? `Duration: ${selectedZoneDuration} minutes` : '',
          mapContext?.insideUsers != null ? `Users inside: ${mapContext.insideUsers}` : ''
        ].filter(Boolean).join('<br>'))
        if (simulation && ['HIGH', 'CRITICAL'].includes(String(selectedZoneRisk || selectedZone?.properties?.risk_level || '').toUpperCase()) && onRiskAreaSelect) {
          selectedLayer.on('click', () => onRiskAreaSelect({
            type: 'configured-zone',
            id: String(selectedZone?.properties?.zone_id || ''),
            risk: String(selectedZoneRisk || selectedZone?.properties?.risk_level || '').toUpperCase(),
            name: selectedZone?.properties?.name || 'Configured zone'
          }))
        }
        selectedLayer.addTo(map)
        overlays.push(selectedLayer)
        const selectedBounds = selectedLayer.getBounds()
        if (selectedBounds.isValid()) {
          map.fitBounds(selectedBounds, { padding: [36, 36], maxZoom: 12, animate: true })
        }
      }

      if (showSimulationLayers && syntheticZone?.geometry) {
        const syntheticLayer = L.geoJSON(syntheticZone, { style: { color: '#fb7185', weight: 4, opacity: 1, fillColor: '#dc2626', fillOpacity: 0.32, dashArray: '10 7' } })
        syntheticLayer.bindTooltip(`DANGER ZONE — ${syntheticZone?.properties?.name || 'Simulation'} — ${syntheticZone?.properties?.risk_level || ''} RISK`, { permanent: true, direction: 'top' })
        syntheticLayer.bindPopup('<b>Generated synthetic zone for simulation.</b><br>Not an official GSI hazard boundary.')
        syntheticLayer.addTo(map)
        overlays.push(syntheticLayer)
        const bounds = syntheticLayer.getBounds()
        if (bounds.isValid()) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 12 })
        const simulationCenter = getCenterFromFeature(syntheticZone)
        if (simulationCenter) {
          const simulationMarker = L.circleMarker(simulationCenter, {
            radius: 10, color: '#ffffff', weight: 3, fillColor: '#ef4444', fillOpacity: 1
          }).bindTooltip(`Simulation Location — ${syntheticZone?.properties?.name || 'Kodagu'}`, { permanent: false, direction: 'top', opacity: 0.95 }).addTo(map)
          overlays.push(simulationMarker)
          simulationMarker.bringToFront()
        }
      }

      // This actor is a simulation overlay, never a GPS/user-location layer.
      if (showSimulationLayers && adminSimulationActor?.status === 'available' && adminSimulationActor?.is_simulation === true) {
        const latitude = Number(adminSimulationActor.latitude)
        const longitude = Number(adminSimulationActor.longitude)
        if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
          const actorMarker = L.marker([latitude, longitude], {
            icon: L.divIcon({ className: 'admin-simulation-actor', iconSize: [24, 24], iconAnchor: [12, 12],
              html: '<span style="display:block;width:20px;height:20px;background:#c084fc;border:3px solid #fff;transform:rotate(45deg);box-shadow:0 0 0 3px #581c87"></span>' }),
            zIndexOffset: 1000,
          }).bindTooltip('ADMIN SIMULATION ACTOR<br />Simulation only &bull; Not real GPS', { permanent: true, direction: 'bottom', opacity: 0.95, className: 'simulation-actor-tooltip' }).addTo(map)
          actorMarker.bindPopup('SIMULATED ADMIN LOCATION. Visualization only; not an SMS recipient. Real saved location is unchanged.')
          overlays.push(actorMarker)
        }
      }

      const simulationPath = showSimulationLayers && simulationRoute?.route?.status === 'ok'
        ? (simulationRoute.route.path || []).map((point) => [Number(point.latitude), Number(point.longitude)]).filter((point) => point.every(Number.isFinite))
        : []
      if (simulationPath.length >= 2) {
        const simulationRouteLayer = L.polyline(simulationPath, {
          color: '#22c55e',
          weight: 6,
          opacity: 0.95
        }).bindTooltip(simulationSafeZone ? '✓ RECOMMENDED SAFE EVACUATION ROUTE — DEMONSTRATION' : 'Simulated Safer Evacuation Route', { sticky: true, opacity: 0.95 }).addTo(map)
        overlays.push(simulationRouteLayer)
        const safeZone = simulationRoute?.safe_zone
        if (Number.isFinite(Number(safeZone?.latitude)) && Number.isFinite(Number(safeZone?.longitude))) {
          overlays.push(L.circleMarker([safeZone.latitude, safeZone.longitude], {
            radius: 9, color: '#ffffff', weight: 3, fillColor: '#22c55e', fillOpacity: 1
          }).bindTooltip(simulationSafeZone ? 'SAFE AREA — simulated assembly area' : 'Safe Destination — verified project location', { direction: 'top', opacity: 0.95 }).addTo(map))
        }
        const simulationRouteBounds = simulationRouteLayer.getBounds()
        if (simulationRouteBounds.isValid()) map.fitBounds(simulationRouteBounds, { padding: [40, 40], maxZoom: 15 })
      }

      affectedUserLocations.forEach((user) => {
        const latitude = Number(user?.latitude)
        const longitude = Number(user?.longitude)
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
        const inside = user?.inside === true
        const marker = L.circleMarker([latitude, longitude], {
          radius: 7,
          color: inside && user?.recipientEligible ? '#38bdf8' : '#ffffff',
          weight: inside && user?.recipientEligible ? 4 : 2,
          fillColor: inside ? (simulationSafeZone ? '#ef4444' : '#22c55e') : '#94a3b8',
          fillOpacity: inside ? 1 : 0.7
        }).addTo(map)
        marker.bindTooltip(`${user?.displayId || 'Registered citizen'}<br>Status: ${inside ? 'Inside selected zone' : 'Outside selected zone'}${inside && user?.recipientEligible ? '<br>Eligible recipient' : ''}`, { direction: 'top', opacity: 0.95 })
        if (simulationSafeZone) {
          const popup = document.createElement('div')
          popup.style.whiteSpace = 'pre-line'
          popup.textContent = `${user.displayId}\nStatus: ${inside ? 'INSIDE DANGER ZONE' : 'OUTSIDE DANGER ZONE'}\nNotification: ${inside ? 'SMS ELIGIBLE' : 'EXCLUDED'}\nSIMULATION ONLY`
          marker.bindPopup(popup)
        }
        marker.bringToFront()
        overlays.push(marker)
      })

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
        marker.bindTooltip('Eligible recipient · Phase 5 preview', { direction: 'top', opacity: 0.95 })
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
        marker.bringToFront()
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
        affectedArea.bindTooltip(`${incidentMode ? 'DEMO INCIDENT' : 'RECENT INCIDENT CONTEXT'} — circular affected area`, { sticky: true, opacity: 0.95 })
        if (simulation && incidentMode && ['HIGH', 'CRITICAL'].includes(String(incidentLocation.risk || risk).toUpperCase()) && incidentLocation.id && onRiskAreaSelect) {
          affectedArea.on('click', () => onRiskAreaSelect({ type: 'incident', id: incidentLocation.id, risk: String(incidentLocation.risk || risk).toUpperCase(), name: incidentLocation.title || 'Incident affected area' }))
        }
        overlays.push(affectedArea)

        const marker = L.circleMarker([incidentLocation.lat, incidentLocation.lng], {
          radius: 12, color: '#ffffff', weight: 3, fillColor: incidentColor, fillOpacity: 1
        }).addTo(map)
        marker.bindTooltip(`🔴 ${incidentMode ? 'SIMULATED INCIDENT' : 'RECENT INCIDENT · DEMO CONTEXT'}<br>${incidentLocation.title || 'Incident location'}<br>${incidentLocation.date || ''}`, { permanent: true, direction: 'top', opacity: 0.95, className: 'admin-incident-tooltip' })
        marker.bindPopup([
          `<b>${incidentMode ? 'SIMULATED INCIDENT' : 'RECENT INCIDENT · DEMO CONTEXT'}</b>`,
          incidentLocation.title || 'Incident location',
          incidentLocation.date ? `Date: ${incidentLocation.date}` : '',
          incidentLocation.location ? `Location: ${incidentLocation.location}` : '',
          `Classification: ${incidentLocation.classification || `${String(incidentLocation.risk || risk).toUpperCase()} — DEMO CLASSIFICATION`}`,
          `Status: ${incidentLocation.status || 'Active simulation'}`,
          incidentLocation.sourceLabel ? `Source: ${incidentLocation.sourceLabel}` : ''
        ].filter(Boolean).join('<br>'), { className: 'admin-incident-popup' })
        overlays.push(marker)
        marker.bringToFront()
        if (incidentMode) map.setView([incidentLocation.lat, incidentLocation.lng], Number(incidentLocation.zoom) || 13, { animate: true })
      }

      if (route?.start && route?.end) {
        const routePath = Array.isArray(route.path) && route.path.length >= 2
          ? route.path
          : [route.start, route.end]
        const routeLayer = L.polyline(routePath, {
          color: '#7dd3fc',
          weight: 4,
          opacity: 0.9,
          dashArray: '10 12'
        }).bindTooltip('Recommended safer route', { sticky: true, opacity: 0.95 }).addTo(map)
        overlays.push(routeLayer)
        overlays.push(L.marker(route.end, {
          icon: L.divIcon({
            className: 'landsense-safezone',
            html: '<div class="safezone-dot"></div>',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
          })
        }).bindTooltip('Destination', { permanent: false, direction: 'top', opacity: 0.95 }).addTo(map))
        const routeBounds = routeLayer.getBounds()
        if (routeBounds.isValid()) map.fitBounds(routeBounds, { padding: [40, 40], maxZoom: 15, animate: true })
      }

      if (route?.start && route?.end) {
        // Route bounds were fitted above after the Citizen explicitly requested guidance.
      } else if (incidentLocation?.lat && incidentLocation?.lng) {
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
      if (showSimulationLayers && simulationSafeZone?.geometry) {
        const safeLayer = L.geoJSON(simulationSafeZone, {
          style: { color: '#22c55e', weight: 3, fillColor: '#22c55e', fillOpacity: 0.25 }
        }).bindTooltip('SAFE AREA — SIMULATED ASSEMBLY AREA', { permanent: true, direction: 'top' }).addTo(map)
        overlays.push(safeLayer)
        // Focus on the local emergency corridor. Affected people are contained
        // by the danger polygon; distant excluded people must not force zoom-out.
        const bounds = safeLayer.getBounds()
        syntheticZone?.geometry?.coordinates?.[0]?.forEach(([lng, lat]) => bounds.extend([lat, lng]))
        simulationPath.forEach(point => bounds.extend(point))
        const fitDemo = () => {
          map.invalidateSize({ pan: false })
          if (bounds.isValid()) map.fitBounds(bounds, { padding: [65, 65], maxZoom: 15, animate: false })
        }
        fitDemo()
        resizeObserver = new ResizeObserver(fitDemo)
        resizeObserver.observe(ref.current)
      }
    }
    
    init().catch(error => {
      if (cancelled) return
      setMapError(simulationSafeZone ? 'Simulation map failed to initialize.' : 'Map failed to initialize.')
      if (import.meta.env.DEV) console.error('LandSense map initialization failed:', error)
    })
    return ()=>{
      cancelled = true
      resizeObserver?.disconnect()
      if (map) {
        const center = map.getCenter()
        viewportRef.current = { latitude: center.lat, longitude: center.lng, zoom: map.getZoom() }
        map.stop()
        // Leaflet's zoom transition schedules a completion after removal. Finish
        // it while panes still exist so a route change cannot access dead panes.
        if (map._animatingZoom) map._onZoomTransitionEnd()
        map.remove()
      }
      mapInstanceRef.current = null
      leafletRef.current = null
      userLocationLayerRef.current = null
      communityReportLayerRef.current = null
      overlays.forEach((layer) => layer?.remove?.())
    }
  }, [zones, simulatedLocation, simulatedCitizens, syntheticZone, simulationRoute, showSimulationLayers, affectedUserLocations, incidentLocation, incidentRadiusMeters, incidentMode, mapContext, route, risk, simulation, selectedZone, selectedZoneRisk, selectedZoneDuration, recipientLocations, landslideRecords, simulationSafeZone, adminSimulationActor])

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

  useEffect(() => {
    const map = mapInstanceRef.current
    const L = leafletRef.current
    const layer = communityReportLayerRef.current
    if (!map || !L || !layer) return
    populateCommunityReportLayer(L, layer, communityReports, showRejectedCommunityReports, showCommunityVerifiedReports)
  }, [communityReports, showRejectedCommunityReports, showCommunityVerifiedReports])

  return <div className="relative h-full w-full">
    {mapError ? <p role="alert" className="absolute inset-0 z-[1000] flex items-center justify-center bg-slate-900 p-6 text-rose-200">{mapError}</p> : null}
    <div ref={ref} className="h-full w-full" aria-label={simulationSafeZone ? 'Simulation map showing danger zone, saved user locations, simulated Admin actor, evacuation route and safe area' : simulation ? 'Map showing real, simulated citizen, and incident locations separately' : 'Map showing configured risk zones, historical landslide inventory, and community reports in a separate layer'} />
    {showSimulationLayers && adminSimulationActor?.status === 'available' ? <div className="simulation-actor-label pointer-events-none absolute left-3 top-3 z-[500] rounded-lg border border-purple-300/40 bg-slate-950/90 px-3 py-2 text-xs text-purple-200"><strong>ADMIN SIMULATION ACTOR</strong><br />Simulation only &bull; Not real GPS</div> : null}
    <div className={`admin-map-legend map-legend pointer-events-none absolute bottom-3 ${simulationSafeZone ? 'right-3' : 'left-3'} z-[500] max-h-[70%] space-y-1 overflow-hidden rounded-lg border border-white/20 bg-slate-950/90 px-3 py-2 text-[10px] text-slate-100 shadow-lg`}>
      <div className="mb-1 font-bold tracking-[0.14em] text-cyan-100">MAP LEGEND</div>
      {zones.length && !incidentMode ? <div><span className="mr-2 inline-block h-2 w-2 rounded-sm border border-rose-300 bg-rose-500/30" />CONFIGURED · Risk zone</div> : null}
      {selectedZone ? <div><span className="mr-2 inline-block h-2 w-2 rounded-sm border-2 border-cyan-300" />SELECTED · Configured zone</div> : null}
      {showSimulationLayers && syntheticZone ? <div><span className="mr-2 inline-block h-2 w-2 rounded-sm border-2 border-rose-300 bg-rose-500/30" />🔴 Simulated Danger Zone</div> : null}
      {showSimulationLayers && simulationRoute?.route?.status === 'ok' ? <><div><span className="mr-2 inline-block h-0.5 w-4 bg-green-500 align-middle" />🟢 Simulated Safer Route</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-green-500" />Safe Destination</div></> : null}
      {showSimulationLayers && syntheticZone ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full border border-white bg-red-500" />📍 Simulation Location</div> : null}
      {incidentLocation ? <><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-red-600" />{incidentMode ? 'SIMULATED' : 'RECENT'} · Incident</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full border border-red-400 bg-red-600/30" />CONTEXT · Circular affected area</div></> : null}
      {affectedUserLocations.some((user) => user.inside) ? <div><span className={`mr-2 inline-block h-2 w-2 rounded-full ${simulationSafeZone ? 'bg-red-500' : 'bg-green-500'}`} />{simulationSafeZone ? 'SIMULATED · Person inside / eligible' : 'REAL · User inside zone'}</div> : null}
      {affectedUserLocations.some((user) => !user.inside) ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-slate-400" />{simulationSafeZone ? 'SIMULATED · Person outside / excluded' : 'REAL · User outside zone'}</div> : null}
      {affectedUserLocations.some((user) => user.recipientEligible) || recipientLocations.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full border-2 border-sky-400 bg-green-500" />TARGETED · Eligible recipient</div> : null}
      {hasValidUserLocation ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-sky-500" />REAL · GPS location</div> : null}
      {route ? <><div><span className="mr-2 inline-block h-0.5 w-4 bg-sky-300 align-middle" />GUIDANCE · Recommended safer route</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-cyan-200" />DESTINATION · User selected</div></> : null}
      {simulatedLocation || simulatedCitizens.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-orange-500" />SIMULATED · Demo citizen</div> : null}
      {landslideRecords.length ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-violet-500" />HISTORICAL · Landslide inventory</div> : null}
      {communityReports.length && showCommunityVerifiedReports ? <><div className="mt-1 border-t border-white/10 pt-1 font-bold text-emerald-200">COMMUNITY VERIFIED · Separate layer</div><div><span className="mr-2 inline-flex h-3 w-3 items-center justify-center rounded-full bg-emerald-700 text-[9px] text-white">✓</span>Approved by admin</div></> : null}
      {communityReports.length && !showCommunityVerifiedReports ? <><div className="mt-1 border-t border-white/10 pt-1 font-bold text-amber-100">COMMUNITY REPORTS · Separate layer</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-yellow-500" />Pending · unverified</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-sky-400" />Under Review</div><div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-green-500" />Verified</div>{showRejectedCommunityReports ? <div><span className="mr-2 inline-block h-2 w-2 rounded-full bg-slate-400" />Rejected · Admin view</div> : null}</> : null}
    </div>
    {mapContext ? <div className="admin-map-context pointer-events-none absolute right-3 top-3 z-[500] max-w-[220px] rounded-lg border border-cyan-200/30 bg-slate-950/90 px-3 py-2 text-[10px] text-slate-100 shadow-lg"><div className="font-bold tracking-[0.12em] text-cyan-100">SELECTED INTELLIGENCE CONTEXT</div><div className="mt-1 text-xs font-semibold">{mapContext.zoneName}</div><div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1"><span className="text-slate-400">Risk</span><b>{mapContext.risk || 'Unavailable'}</b><span className="text-slate-400">Users inside</span><b>{mapContext.insideUsers ?? 'Unavailable'}</b><span className="text-slate-400">Recipients</span><b>{mapContext.recipientCount ?? 'Unavailable'}</b><span className="text-slate-400">Recent incident</span><b>{mapContext.incidentStatus}</b></div></div> : !simulationSafeZone && !selectedZone && !incidentLocation ? <div className="admin-map-context pointer-events-none absolute right-3 top-3 z-[500] max-w-[210px] rounded-lg border border-white/15 bg-slate-950/85 px-3 py-2 text-xs text-slate-300 shadow-lg">Select a configured zone to view its intelligence context.</div> : null}
    {showSimulationLayers ? <div className="pointer-events-none absolute left-14 top-3 z-[500] rounded-lg border border-amber-200/40 bg-amber-500/90 px-2.5 py-1 text-xs font-bold tracking-wide text-slate-950 shadow-lg">⚠ SIMULATION MODE — DEMONSTRATION ONLY</div> : simulation ? <div className="pointer-events-none absolute left-14 top-3 z-[500] rounded-lg border border-amber-200/40 bg-amber-500/90 px-2.5 py-1 text-xs font-bold tracking-wide text-slate-950 shadow-lg">SIMULATION</div> : null}
  </div>
}
