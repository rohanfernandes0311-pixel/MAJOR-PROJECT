import { useEffect, useRef } from 'react'
import 'leaflet/dist/leaflet.css'

const RISK_STYLES = {
  SAFE: { fill: '#22c55e', stroke: '#34d399', heat: 'rgba(34,197,94,0.18)' },
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

export default function MapView({ zones = [], userLocation = null, route = null, risk = 'SAFE' }){
  const ref = useRef()

  useEffect(()=>{
    let L
    let map
    let overlays = []
    
    async function init(){
      L = (await import('leaflet')).default
      if(!ref.current) return
      
      map = L.map(ref.current, { zoomControl: true, attributionControl: false, preferCanvas: true }).setView([14.5, 76.2], 6)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map)

      const currentRiskStyle = RISK_STYLES[risk] || RISK_STYLES.SAFE

      const geoLayer = L.geoJSON({ type: 'FeatureCollection', features: zones }, {
        style: (feature) => getFeatureStyle(feature, currentRiskStyle),
        onEachFeature: (feature, layer) => {
          const name = feature?.properties?.name || 'Risk zone'
          const level = feature?.properties?.risk_level || 'SAFE'
          layer.bindTooltip(`${name} • ${level}`, { sticky: true, direction: 'top', opacity: 0.95 })
        }
      }).addTo(map)
      overlays.push(geoLayer)

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

      if (userLocation?.lat && userLocation?.lng) {
        const marker = L.circleMarker([userLocation.lat, userLocation.lng], {
          radius: 9,
          color: '#ffffff',
          weight: 2,
          fillColor: '#22c55e',
          fillOpacity: 1
        }).addTo(map)
        marker.bindTooltip('You are here', { permanent: false, direction: 'top', opacity: 0.95 })
        overlays.push(marker)

        overlays.push(L.circle([userLocation.lat, userLocation.lng], {
          radius: 5000,
          color: '#22c55e',
          fillColor: '#22c55e',
          fillOpacity: 0.08,
          weight: 1,
          className: 'landsense-pulse'
        }).addTo(map))
      }

      if (route?.start && route?.end) {
        overlays.push(L.polyline([route.start, route.end], {
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

      if (userLocation?.lat && userLocation?.lng) {
        map.setView([userLocation.lat, userLocation.lng], 9, { animate: true })
      } else if (zones.length) {
        const first = getCenterFromFeature(zones[0])
        if (first) map.setView(first, 7, { animate: true })
      }
    }
    
    init()
    return ()=>{ overlays.forEach((layer) => layer?.remove?.()); if(map) map.remove() }
  }, [zones, userLocation, route, risk])

  return <div ref={ref} className="w-full h-full" aria-label="Live map showing nearby risk" />
}
