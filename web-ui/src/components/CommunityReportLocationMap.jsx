import { useEffect, useRef } from 'react'
import { isWithinKarnatakaBounds } from '../services/communityReportsFeature'

const INITIAL_CENTER = [15.3173, 76.7139]

export default function CommunityReportLocationMap({ location, onLocationChange }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const leafletRef = useRef(null)
  const markerRef = useRef(null)
  const callbackRef = useRef(onLocationChange)
  const locationRef = useRef(location)
  callbackRef.current = onLocationChange
  locationRef.current = location

  useEffect(() => {
    let cancelled = false
    let resizeObserver

    async function initializeMap() {
      const leafletModule = await import('leaflet')
      if (cancelled || !containerRef.current) return
      const L = leafletModule.default || leafletModule
      const initial = locationRef.current
      const hasLocation = initial?.valid && isWithinKarnatakaBounds(initial.latitude, initial.longitude)
      const map = L.map(containerRef.current, { scrollWheelZoom: false })
        .setView(hasLocation ? [initial.latitude, initial.longitude] : INITIAL_CENTER, hasLocation ? 13 : 6)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map)
      map.on('click', (event) => callbackRef.current?.({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      }))
      mapRef.current = map
      leafletRef.current = L

      if (hasLocation) updateMarker(L, map, initial)
      resizeObserver = typeof ResizeObserver === 'function'
        ? new ResizeObserver(() => map.invalidateSize())
        : null
      resizeObserver?.observe(containerRef.current)
      window.requestAnimationFrame(() => map.invalidateSize())
    }

    function updateMarker(L, map, selectedLocation) {
      if (!selectedLocation?.valid || !isWithinKarnatakaBounds(selectedLocation.latitude, selectedLocation.longitude)) return
      if (!markerRef.current) {
        markerRef.current = L.marker([selectedLocation.latitude, selectedLocation.longitude], {
          draggable: true,
          icon: L.divIcon({
            className: '',
            html: '<span style="display:block;width:20px;height:20px;border:3px solid white;border-radius:50% 50% 50% 0;background:#087f5b;box-shadow:0 1px 5px #334155;transform:rotate(-45deg)"></span>',
            iconSize: [22, 22],
            iconAnchor: [11, 20],
          }),
        }).addTo(map)
        markerRef.current.on('dragend', (event) => {
          const point = event.target.getLatLng()
          callbackRef.current?.({ latitude: point.lat, longitude: point.lng })
        })
      } else {
        markerRef.current.setLatLng([selectedLocation.latitude, selectedLocation.longitude])
      }
      map.setView([selectedLocation.latitude, selectedLocation.longitude], Math.max(map.getZoom(), 13), { animate: true })
    }

    initializeMap().catch(() => {})
    return () => {
      cancelled = true
      resizeObserver?.disconnect()
      markerRef.current = null
      mapRef.current?.remove()
      mapRef.current = null
      leafletRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const L = leafletRef.current
    if (!map || !L) return
    if (!location?.valid) {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    if (!isWithinKarnatakaBounds(location.latitude, location.longitude)) return
    if (!markerRef.current) {
      const marker = L.marker([location.latitude, location.longitude], {
        draggable: true,
        icon: L.divIcon({
          className: '',
          html: '<span style="display:block;width:20px;height:20px;border:3px solid white;border-radius:50% 50% 50% 0;background:#087f5b;box-shadow:0 1px 5px #334155;transform:rotate(-45deg)"></span>',
          iconSize: [22, 22],
          iconAnchor: [11, 20],
        }),
      }).addTo(map)
      marker.on('dragend', (event) => {
        const point = event.target.getLatLng()
        callbackRef.current?.({ latitude: point.lat, longitude: point.lng })
      })
      markerRef.current = marker
    } else {
      markerRef.current.setLatLng([location.latitude, location.longitude])
    }
    map.flyTo([location.latitude, location.longitude], Math.max(map.getZoom(), 13))
  }, [location?.valid, location?.latitude, location?.longitude])

  return <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
    <div className="flex items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2">
      <span className="text-xs font-semibold text-slate-700">Choose report location</span>
      <span className="text-[10px] text-slate-500">Karnataka, India</span>
    </div>
    <div ref={containerRef} className="h-64 w-full sm:h-72" aria-label="Choose a Karnataka report location on the map" />
    <p className="bg-white px-3 py-2 text-[11px] text-slate-500">Select a place, click the map, or drag the marker to fine-tune.</p>
  </div>
}
