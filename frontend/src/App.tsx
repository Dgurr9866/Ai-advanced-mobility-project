// React hooks for managing the map's lifecycle
// and accessing the HTML container.
import { useEffect, useRef } from 'react'

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
    })

    // Destroy the map when the component unmounts
    // to prevent memory and resource leaks.
    return () => map.remove()

  }, []) // Empty dependency array prevents reinitialization on updates.

  // Render the HTML container for the map.
  return <div ref={mapContainer} className="map" />
}

// Export the main application component.
export default App