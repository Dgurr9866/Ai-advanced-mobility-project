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

  // used for weather
  const mapInstance = useRef<maplibregl.Map | null>(null)
  const [weatherMode, setWeatherMode] = useState<'simulated' | 'live'>('simulated')
  const [timeStepHours, setTimeStepHours] = useState<number>(0)

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
      //add weather grid 
      map.addSource('weather-grid', {
        type: 'geojson',
        data: {
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
            'case',
            // 1. Extreme Storm (Instant/High Crash Zone)
            ['any', ['>', ['get', 'wind_speed_mph'], 50], ['>', ['get', 'rain_inches_per_hour'], 1.5]],
            '#a21caf', // Deep Magenta

            // 2. Severe Storm (Crash Threshold in drone.py: >40 mph or >1.0 in/hr)
            ['any', ['>', ['get', 'wind_speed_mph'], 40], ['>', ['get', 'rain_inches_per_hour'], 1.0]],
            '#dc2626', // Crimson Red

            // 3. Heavy Squall / High Gusts
            ['any', ['>', ['get', 'wind_speed_mph'], 33], ['>', ['get', 'rain_inches_per_hour'], 0.65]],
            '#ea580c', // Dark Orange

            // 4. Strong Wind / Steady Rain
            ['any', ['>', ['get', 'wind_speed_mph'], 26], ['>', ['get', 'rain_inches_per_hour'], 0.35]],
            '#f59e0b', // Amber / Light Orange

            // 5. Moderate Wind / Light Rain
            ['any', ['>', ['get', 'wind_speed_mph'], 20], ['>', ['get', 'rain_inches_per_hour'], 0.15]],
            '#eab308', // Yellow

            // 6. Fresh Breeze / Drizzle
            ['any', ['>', ['get', 'wind_speed_mph'], 14], ['>', ['get', 'rain_inches_per_hour'], 0.05]],
            '#22c55e', // Emerald Green

            // 7. Gentle Breeze
            ['>', ['get', 'wind_speed_mph'], 8],
            '#06b6d4', // Cyan / Teal

            // 8. Calm Air
            '#82b2ff', // Soft Blue
          ],
          'fill-opacity': 0.45,
          'fill-antialias': false,
        },
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
      })

    return () => controller.abort()
  }, [weatherMode, timeStepHours])

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

      <div ref={mapContainer} className="map" style={{ flex: 1 }} />
    </div>
  )
}

// Export the main application component.
export default App
