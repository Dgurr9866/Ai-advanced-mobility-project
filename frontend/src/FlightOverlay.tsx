// frontend/src/FlightOverlay.tsx
import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'

interface FlightOverlayProps {
  map: maplibregl.Map | null
  weatherMode: 'simulated' | 'live'
  timeStepHours: number
  onTimeChange: (hours: number) => void
}

const API_BASE = 'http://localhost:8000'

const CITY_PRESETS: Record<string, [number, number]> = {
  Miami: [-80.1918, 25.7617],
  Orlando: [-81.3792, 28.5383],
  Tampa: [-82.4572, 27.9506],
  Jacksonville: [-81.6557, 30.3322],
  Tallahassee: [-84.2807, 30.4383],
  'Fort Myers': [-81.8723, 26.6406],
}

const EMPTY_GEOJSON = {
  type: 'FeatureCollection' as const,
  features: [],
}

export function FlightOverlay({
  map,
  weatherMode,
  timeStepHours,
  onTimeChange,
}: FlightOverlayProps) {
  const [startCity, setStartCity] = useState('Miami')
  const [goalCity, setGoalCity] = useState('Jacksonville')
  const [plan, setPlan] = useState<any>(null)
  const [flightResult, setFlightResult] = useState<any>(null)
  const [liveTelemetry, setLiveTelemetry] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const lastWeatherTimeRef = useRef<number>(-1)
  const checkpointMarkersRef = useRef<maplibregl.Marker[]>([]) // <-- ADD THIS  

  const animationRef = useRef<number | null>(null)
  const droneMarkerRef = useRef<maplibregl.Marker | null>(null)

  const stopAnimation = () => {
    if (animationRef.current !== null) {
      window.clearInterval(animationRef.current)
      animationRef.current = null
    }
    setIsAnimating(false)
  }

  // Creates, moves, or removes the floating HTML drone marker
  const updateDroneMarker = (coords: [number, number] | null) => {
    if (!map) return
    if (!coords) {
      droneMarkerRef.current?.remove()
      droneMarkerRef.current = null
      return
    }
    if (!droneMarkerRef.current) {
      const el = document.createElement('div')
      el.style.width = '16px'
      el.style.height = '16px'
      el.style.borderRadius = '50%'
      el.style.backgroundColor = '#2563eb'
      el.style.border = '3px solid #ffffff'
      el.style.boxShadow = '0 0 8px rgba(37, 99, 235, 0.9)'
      droneMarkerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat(coords)
        .addTo(map)
    } else {
      droneMarkerRef.current.setLngLat(coords)
    }
  }

  const clearCheckpointMarkers = () => {
    checkpointMarkersRef.current.forEach((m) => m.remove())
    checkpointMarkersRef.current = []
  }

  const showCheckpointMarkers = (checkpoints: any[]) => {
    clearCheckpointMarkers()
    if (!map || !checkpoints) return

    checkpoints.forEach((cp) => {
      const badge = document.createElement('div')
      badge.textContent = `+${cp.time_hours}h`
      badge.style.backgroundColor = 'rgba(15, 23, 42, 0.9)'
      badge.style.color = '#f8fafc'
      badge.style.fontSize = '11px'
      badge.style.fontWeight = '700'
      badge.style.padding = '2px 6px'
      badge.style.borderRadius = '10px'
      badge.style.border = cp.danger >= 20 ? '2px solid #f59e0b' : '1px solid #94a3b8'
      badge.style.cursor = 'pointer'
      badge.style.boxShadow = '0 2px 6px rgba(0,0,0,0.4)'

      // Clicking a badge previews the weather and drone position at that hour
      badge.addEventListener('click', () => {
        const snappedTime = Math.round(cp.time_hours * 2) / 2
        onTimeChange(snappedTime)
        updateDroneMarker(cp.coordinates)
      })

      const marker = new maplibregl.Marker({ element: badge })
        .setLngLat(cp.coordinates)
        .addTo(map)

      checkpointMarkersRef.current.push(marker)
    })
  }

  // Ensures the route and trail layers exist on top of the weather grid
  const ensureFlightLayers = (targetMap: maplibregl.Map): boolean => {
    if (!targetMap.isStyleLoaded()) return false

    if (!targetMap.getSource('planned-route')) {
      targetMap.addSource('planned-route', { type: 'geojson', data: EMPTY_GEOJSON })
      targetMap.addLayer({
        id: 'planned-route-line',
        type: 'line',
        source: 'planned-route',
        paint: {
          'line-color': '#0f172a',
          'line-width': 3.5,
          'line-dasharray': [2, 2],
        },
      })
    }

    if (!targetMap.getSource('flown-trail')) {
      targetMap.addSource('flown-trail', { type: 'geojson', data: EMPTY_GEOJSON })
      targetMap.addLayer({
        id: 'flown-trail-line',
        type: 'line',
        source: 'flown-trail',
        paint: {
          'line-color': '#2563eb',
          'line-width': 5,
        },
      })
    }

    // Keep route and trail above the weather heatmap
    if (targetMap.getLayer('planned-route-line')) targetMap.moveLayer('planned-route-line')
    if (targetMap.getLayer('flown-trail-line')) targetMap.moveLayer('flown-trail-line')

    return true
  }

  useEffect(() => {
    if (!map) return

    const onReady = () => ensureFlightLayers(map)
    onReady()

    map.on('load', onReady)
    map.on('style.load', onReady)

    return () => {
      map.off('load', onReady)
      map.off('style.load', onReady)
      stopAnimation()
      updateDroneMarker(null)
      clearCheckpointMarkers()
    }
  }, [map])

  const setSourceData = (sourceId: string, data: any) => {
    if (!map) return
    ensureFlightLayers(map)
    const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined
    source?.setData(data)
  }

  const clearFlight = () => {
    stopAnimation()
    setPlan(null)
    setFlightResult(null)
    setLiveTelemetry(null)
    setSourceData('planned-route', EMPTY_GEOJSON)
    setSourceData('flown-trail', EMPTY_GEOJSON)
    updateDroneMarker(null)
    clearCheckpointMarkers()
  }

  // 1. Pre-flight HITL step: request A* plan & preview on map
  const handlePlanFlight = async () => {
    stopAnimation()
    setFlightResult(null)
    setLiveTelemetry(null)
    setIsLoading(true)
    onTimeChange(0) // <-- Reset the time slider to 0

    const [startLon, startLat] = CITY_PRESETS[startCity]
    const [goalLon, goalLat] = CITY_PRESETS[goalCity]

    try {
      const params = new URLSearchParams({
        start_lon: String(startLon),
        start_lat: String(startLat),
        goal_lon: String(goalLon),
        goal_lat: String(goalLat),
        mode: weatherMode,
        time_step_hours: '0', // <-- Always start new flights at time 0
      })
      const res = await fetch(`${API_BASE}/api/flight/plan?${params}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to plan flight')

      setPlan(data)
      setSourceData('planned-route', data.route_geojson)
      setSourceData('flown-trail', EMPTY_GEOJSON)
      updateDroneMarker(data.start)
      showCheckpointMarkers(data.route_geojson.properties.time_checkpoints)
    } catch (err) {
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // 2. Operator approves plan -> run simulation & animate drone
  const handleApproveAndLaunch = async () => {
    if (!plan?.flight_id) return
    setIsLoading(true)

    try {
      const params = new URLSearchParams({
        flight_id: plan.flight_id,
        mode: weatherMode,
      })
      const res = await fetch(`${API_BASE}/api/flight/run?${params}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to run flight')

      setFlightResult(data)
      clearCheckpointMarkers()
      animateTrail(
        data.drone.flown_trail_geojson.geometry.coordinates,
        data.drone.telemetry_log
      )
    } catch (err) {
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const animateTrail = (coords: number[][], telemetry: any[]) => {
    stopAnimation()
    if (!coords || coords.length < 2) return

    lastWeatherTimeRef.current = -1
    setIsAnimating(true)
    updateDroneMarker(coords[0] as [number, number])
    let step = 1

    animationRef.current = window.setInterval(() => {
      const slice = coords.slice(0, step + 1)
      const latestPos = slice[slice.length - 1]

      setSourceData('flown-trail', {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: slice },
        properties: {},
      })
      updateDroneMarker(latestPos as [number, number])

      if (telemetry?.[step - 1]) {
        const currentTelemetry = telemetry[step - 1]
        setLiveTelemetry(currentTelemetry)

        // Update the weather slider every 0.5 simulated hours
        const snappedTime = Math.round(currentTelemetry.time_hours * 2) / 2
        if (snappedTime !== lastWeatherTimeRef.current) {
          lastWeatherTimeRef.current = snappedTime
          onTimeChange(snappedTime)
        }
      }

      step += 1
      if (step >= coords.length) {
        stopAnimation()
      }
    }, 55)
  }

  return (
    <>
      {/* Top-Left Flight Controls */}
      <div
        style={{
          position: 'absolute',
          top: '14px',
          left: '14px',
          backgroundColor: 'rgba(15, 23, 42, 0.92)',
          backdropFilter: 'blur(6px)',
          color: '#f8fafc',
          padding: '12px 14px',
          borderRadius: '8px',
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.3)',
          fontSize: '12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          zIndex: 15,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: '13px' }}>Flight Planner</div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <select value={startCity} onChange={(e) => setStartCity(e.target.value)}>
            {Object.keys(CITY_PRESETS).map((city) => (
              <option key={city} value={city}>
                From: {city}
              </option>
            ))}
          </select>

          <select value={goalCity} onChange={(e) => setGoalCity(e.target.value)}>
            {Object.keys(CITY_PRESETS).map((city) => (
              <option key={city} value={city}>
                To: {city}
              </option>
            ))}
          </select>

          <button
            onClick={handlePlanFlight}
            disabled={isLoading}
            style={{
              backgroundColor: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              padding: '5px 10px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Plan Flight
          </button>
        </div>
      </div>

      {/* Pre-Flight HITL Approval Card */}
      {plan && !flightResult && (
        <div
          style={{
            position: 'absolute',
            top: '96px',
            left: '14px',
            maxWidth: '320px',
            backgroundColor: 'rgba(15, 23, 42, 0.96)',
            color: '#f8fafc',
            padding: '14px 16px',
            borderRadius: '8px',
            borderLeft: '4px solid #22c55e',
            boxShadow: '0 6px 20px rgba(0, 0, 0, 0.4)',
            fontSize: '12px',
            lineHeight: 1.5,
            zIndex: 20,
          }}
        >
          <div style={{ fontWeight: 700, color: '#4ade80', marginBottom: '6px' }}>
            Approve Flight Plan ({startCity} → {goalCity})
          </div>
          <div style={{ color: '#cbd5e1', marginBottom: '10px' }}>
            Distance: <b>{plan.summary.distance_miles} mi</b>
            <br />
            Est. Arrival Battery: <b>{plan.summary.estimated_arrival_battery}%</b>
            <br />
            Max Forecast Danger: <b>{plan.summary.max_danger}</b>
          </div>

        <div style={{ fontSize: '11px', color: '#93c5fd', marginBottom: '10px' }}>
            Tip: Click any <b>+Xh</b> badge on the route to preview weather at that time.
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleApproveAndLaunch}
              disabled={isLoading}
              style={{
                backgroundColor: '#22c55e',
                color: '#0f172a',
                fontWeight: 700,
                border: 'none',
                borderRadius: '4px',
                padding: '6px 12px',
                cursor: 'pointer',
              }}
            >
              Approve &amp; Launch
            </button>

            <button
              onClick={clearFlight}
              style={{
                backgroundColor: '#334155',
                color: '#f8fafc',
                border: 'none',
                borderRadius: '4px',
                padding: '6px 12px',
                cursor: 'pointer',
              }}
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Live Telemetry & Final Status Card */}
      {flightResult && (
        <div
          style={{
            position: 'absolute',
            top: '96px',
            left: '14px',
            maxWidth: '330px',
            backgroundColor: 'rgba(15, 23, 42, 0.92)',
            color: '#f8fafc',
            padding: '12px 14px',
            borderRadius: '8px',
            fontSize: '12px',
            lineHeight: 1.5,
            zIndex: 15,
          }}
        >
          <div>
            <b>Status:</b>{' '}
            {isAnimating
              ? 'IN_FLIGHT — En route...'
              : `${flightResult.drone.status} — ${flightResult.drone.status_reason}`}
          </div>
          {liveTelemetry && (
            <div style={{ color: '#93c5fd', marginTop: '4px' }}>
              t=+{liveTelemetry.time_hours}h | Battery: <b>{liveTelemetry.battery_percent}%</b> |
              Speed: {liveTelemetry.groundspeed_mph} mph
            </div>
          )}
        </div>
      )}
    </>
  )
}