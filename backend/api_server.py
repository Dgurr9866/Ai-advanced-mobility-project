from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from weather_providers import SimulatedFloridaWeather, LiveFloridaWeather
from florida_map_grid import FloridaAirspaceGrid
from geo_utils import FLORIDA_GEOJSON_PATH, NO_FLY_ZONES_GEOJSON_PATH

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Florida landmass & subtract FAA Restricted/Prohibited No-Fly Zones once on startup
airspace_grid = FloridaAirspaceGrid(
    florida_geojson_path=FLORIDA_GEOJSON_PATH,
    no_fly_zones_geojson_path=NO_FLY_ZONES_GEOJSON_PATH,
    cell_size_miles=5.0,
)

simulated_weather = SimulatedFloridaWeather.generate_random_scenario(num_storms=5)
live_weather = None


@app.get("/api/weather")
def get_weather_layer(mode: str = "simulated", time_step_hours: float = 0.0):
    global live_weather
    if mode == "live":
        if live_weather is None:
            live_weather = LiveFloridaWeather()
        provider = live_weather
    else:
        provider = simulated_weather

    return airspace_grid.export_danger_grid_geojson(
        provider, time_step_hours=time_step_hours
    )