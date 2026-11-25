// React hooks for managing the map's lifecycle
// and accessing the HTML container.
import { useEffect, useRef, useState } from 'react'

// MapLibre library for rendering interactive vector maps.
import * as maplibregl from 'maplibre-gl'

// Default styling for MapLibre controls and components.
import 'maplibre-gl/dist/maplibre-gl.css'

// Custom application styling.
import './App.css'

// Import the background worker used to process map data.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

// Configure MapLibre to use the worker bundled by Vite.
maplibregl.setWorkerUrl(workerUrl)

function App() {
  // Reference to the HTML element that will contain the map.
  const mapContainer = useRef<HTMLDivElement>(null)

  //shared colors for the key and map
  const DANGER_COLOR_STOPS: Array<[number, string, string]> = [
    [500, '#701a75', 'Crash Zone (500+)'],
    [100, '#991b1b', 'Extreme (100)'],
    [40,  '#ef4444', 'Severe (40)'],
    [25,  '#f97316', 'High Penalty (25)'],
    [15,  '#eab308', 'Moderate (15)'],
    [8,   '#84cc16', 'Low Risk (8)'],
    [0,   '#10b981', 'Optimal (0)'],
  ]

  // Ascending stops for MapLibre ['interpolate', ...]
  const ASCENDING_INTERPOLATE_STOPS = [...DANGER_COLOR_STOPS]
    .reverse()
    .flatMap(([value, color]) => [value, color]) as [number | string, ...(number | string)[]]

  // Top-to-bottom CSS gradient string derived from DANGER_COLOR_STOPS
  const LEGEND_GRADIENT = `linear-gradient(to bottom, ${DANGER_COLOR_STOPS.map(
    ([, color], index) => `${color} ${(index / (DANGER_COLOR_STOPS.length - 1)) * 100}%`
  ).join(', ')})`

  // used for weather
  const mapInstance = useRef<maplibregl.Map | null>(null)
  const latestWeatherRef = useRef<maplibregl.GeoJSONSourceSpecification['data'] | null>(null)
  const [weatherMode, setWeatherMode] = useState<'simulated' | 'live'>('simulated')
  const [timeStepHours, setTimeStepHours] = useState<number>(0)

  // variables for route planning
  // goal points are temporarily hardcoded for testing purposes
  const [startPoint, setStartPoint] = useState<[number, number]>([-81.3792, 28.5383]) // Orlando
  const [goalPoint, setGoalPoint] = useState<[number, number]>([-82.4572, 27.9506])   // Tampa
  const [clickTarget, setClickTarget] = useState<'start' | 'goal'>('goal')
  const [routeStats, setRouteStats] = useState<{ distance_miles?: number; max_danger?: number } | null>(null)

  // Initialize the map after the component has mounted.
  useEffect(() => {

    // Ensure the HTML container exists before creating the map.
    if (!mapContainer.current) return

    // Create the interactive vector map.
    const map = new maplibregl.Map({
      container: mapContainer.current,

      // Vector map style provided by OpenFreeMap.
      style: 'https://tiles.openfreemap.org/styles/positron',

      // Initial map center (longitude, latitude).
      center: [-81.5, 27.8],

      // Initial zoom level.
      zoom: 6,
      
      // Prevent zooming out beyond the initial zoom level.
      minZoom: 6,

      // Restrict map movement to the Florida region.
      maxBounds: [
        [-92, 23.8], // Southwest boundary
        [-75, 32.5]  // Northeast boundary
      ]
    })

    // Add zoom and compass controls.
    map.addControl(new maplibregl.NavigationControl())
    
    // Wait for the map to finish loading.
    map.on('load', () => {
      // Add a source for the planned route, initially empty.
      map.addSource('planned-route', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      // Draw the planned route as a black line.
      map.addLayer({
        id: 'planned-route-line',
        type: 'line',
        source: 'planned-route',
        paint: {
          'line-color': '#111827',
          'line-width': 4,
        },
      })

      //add weather grid 
      map.addSource('weather-grid', {
        type: 'geojson',
        data: latestWeatherRef.current ?? {
          type: 'FeatureCollection',
          features: [],
        },
      })

      map.addLayer({
        id: 'weather-fill',
        type: 'fill',
        source: 'weather-grid',
        paint: {
          'fill-color': [
            'interpolate',
            ['linear'],
            ['get', 'danger_value'],
            ...ASCENDING_INTERPOLATE_STOPS,
          ],
          'fill-opacity': 0.45,
          'fill-antialias': false,
        },
      })
      
      fetch('http://localhost:8000/routes/test')
      .then(response => {
        if (!response.ok) {
          throw new Error('Failed to fetch route')
        }
        return response.json()
      })
      .then(route => {

        // Add the route data to MapLibre
        map.addSource('test-route', {
          type: 'geojson',
          data: route
        })

        // Draw the route as a red line
        map.addLayer({
          id: 'test-route-line',
          type: 'line',
          source: 'test-route',
          paint: {
            'line-color': '#FF0000',
            'line-width': 4
          }
        })

        console.log('Drone route loaded:', route)
      })
      .catch(error => {
        console.error('Error loading drone route:', error)
      })

      // Register Florida's geographical boundary data.
      map.addSource('florida', {
        type: 'geojson',
        data: '/data/florida.geojson'
      })
      // Draw an outline around Florida's geographical boundary.
      map.addLayer({
        id: 'florida-border',
        type: 'line',
        source: 'florida',
        paint: {
          'line-color': '#000000',
          'line-width': 3,
          'line-opacity': 0.4
        }
      })

      mapInstance.current = map
    })

    // Destroy the map when the component unmounts
    // to prevent memory and resource leaks.
    return () => {
      mapInstance.current = null
      map.remove()
    }

  }, []) // Empty dependency array prevents reinitialization on updates.

  // contacts the weather api to update the map
  useEffect(() => {
    const controller = new AbortController()

    fetch(
      `http://localhost:8000/api/weather?mode=${weatherMode}&time_step_hours=${timeStepHours}`,
      { signal: controller.signal }
    )
      .then((response) => response.json())
      .then((weatherGeoJson) => {
        const source = mapInstance.current?.getSource('weather-grid') as
          | maplibregl.GeoJSONSource
          | undefined
        if (source) {
          source.setData(weatherGeoJson)
        }
      })
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') {
          console.error('Failed to fetch weather layer:', error)
        }
      }).then((weatherGeoJson) => {
      latestWeatherRef.current = weatherGeoJson
      const source = mapInstance.current?.getSource('weather-grid') as
        | maplibregl.GeoJSONSource
        | undefined
      if (source) {
        source.setData(weatherGeoJson)
      }
    })

    return () => controller.abort()
  }, [weatherMode, timeStepHours])

  // handles the route planning api call and updates the map with the new route
  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({
      start_lon: String(startPoint[0]),
      start_lat: String(startPoint[1]),
      goal_lon: String(goalPoint[0]),
      goal_lat: String(goalPoint[1]),
      mode: weatherMode,
      time_step_hours: String(timeStepHours),
    })

    fetch(`http://localhost:8000/api/route?${params.toString()}`, {
      signal: controller.signal,
    })
      .then((res) => res.json())
      .then((routeFeature) => {
        if (routeFeature?.geometry) {
          setRouteStats(routeFeature.properties)
          const source = mapInstance.current?.getSource('planned-route') as
            | maplibregl.GeoJSONSource
            | undefined
          if (source) {
            source.setData(routeFeature)
          }
        }
      })
      .catch((err) => {
        if ((err as Error).name !== 'AbortError') {
          console.error('Route error:', err)
        }
      })

    return () => controller.abort()
  }, [startPoint, goalPoint, weatherMode, timeStepHours])

  // Render the HTML container for the map.
  // extra stuff for weather
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw' }}>
      <div style={{ display: 'flex', gap: '16px', padding: '10px', backgroundColor: '#1e293b', color: '#fff' }}>
        <select
          value={weatherMode}
          onChange={(event) => {
            const source = mapInstance.current?.getSource('weather-grid') as
              | maplibregl.GeoJSONSource
              | undefined
            if (source) {
              source.setData({ type: 'FeatureCollection', features: [] })
            }
            setWeatherMode(event.target.value as 'simulated' | 'live')
          }}
        >
          <option value="simulated">Simulated Storms</option>
          <option value="live">Live Forecast</option>
        </select>

        <label>
          Time: +{timeStepHours.toFixed(1)} hrs{' '}
          <input
            type="range"
            min={0}
            max={6}
            step={0.5}
            value={timeStepHours}
            onChange={(event) => setTimeStepHours(parseFloat(event.target.value))}
          />
        </label>
      </div>

      
        <div style={{ position: 'relative', flex: 1, minHeight: 0, width: '100%' }}>
        <div
          ref={mapContainer}
          style={{ position: 'absolute', inset: 0 }}
        />

        {/* Vertical Side Legend */}
        <div
          style={{
            position: 'absolute',
            bottom: '28px',
            right: '16px',
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            backdropFilter: 'blur(6px)',
            color: '#f8fafc',
            padding: '12px 14px',
            borderRadius: '8px',
            boxShadow: '0 4px 14px rgba(0, 0, 0, 0.3)',
            fontSize: '12px',
            zIndex: 10,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '10px', fontSize: '13px' }}>
            Airspace Danger
          </div>

          <div style={{ display: 'flex', alignItems: 'stretch', gap: '10px' }}>
            {/* Vertical Continuous Gradient Bar */}
            <div
              style={{
                width: '12px',
                borderRadius: '4px',
                background: LEGEND_GRADIENT,
              }}
            />

            {/* Name & Value Labels */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              {DANGER_COLOR_STOPS.map(([value, , label]) => (
                <span key={value} style={{ lineHeight: 1 }}>
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      
    </div>
  )
}

// Export the main application component.
export default App
