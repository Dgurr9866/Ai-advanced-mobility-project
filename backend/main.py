from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from weather_providers import SimulatedFloridaWeather, LiveFloridaWeather
from florida_map_grid import FloridaAirspaceGrid
from geo_utils import (
    FLORIDA_GEOJSON_PATH,
    NO_FLY_ZONES_GEOJSON_PATH,
    haversine_miles,
)
from citygraph import City
from global_path_planner import RouteConfig, find_safest_route


app = FastAPI(title="Florida Drone Safety Simulator")

# Allow the local React frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

#only calculates/lookups once
weather_grid_cache: dict[tuple[str, float], dict] = {}

# Load Florida landmass & subtract FAA Restricted/Prohibited No-Fly Zones once on startup
airspace_grid = FloridaAirspaceGrid(
    florida_geojson_path=str(FLORIDA_GEOJSON_PATH),
    no_fly_zones_geojson_path=(
        str(NO_FLY_ZONES_GEOJSON_PATH) if NO_FLY_ZONES_GEOJSON_PATH.exists() else None
    ),
    cell_size_miles=5.0,
)

simulated_weather = SimulatedFloridaWeather.generate_random_scenario(num_storms=6)
live_weather = None

def _get_weather_provider(mode: str):
    global live_weather
    if mode == "live":
        if live_weather is None:
            try:
                live_weather = LiveFloridaWeather()
            except Exception as error:
                print(f"Open-Meteo unavailable ({error}), falling back to simulated weather")
                return simulated_weather
        return live_weather
    return simulated_weather

@app.get("/")
def home():
    return {
        "message": "Florida Drone Safety Simulator API"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/weather")
def get_weather_layer(mode: str = "simulated", time_step_hours: float = 0.0):
    provider = _get_weather_provider(mode)
    return airspace_grid.export_danger_grid_geojson(
        provider, time_step_hours=time_step_hours
    )


@app.get("/routes/test")
def test_route():
    orlando = City("Orlando", 28.5383, -81.3792)
    tampa = City("Tampa", 27.9506, -82.4572)

    distance = haversine_miles(
        orlando.longitude, orlando.latitude,
        tampa.longitude, tampa.latitude,
    )

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [orlando.longitude, orlando.latitude],
                [tampa.longitude, tampa.latitude],
            ],
        },
        "properties": {
            "origin": orlando.name,
            "destination": tampa.name,
            "distance_miles": round(distance, 2),
            "route_type": "test",
        },
    }


#calls the pathfinder in global_path_planner.py to find the safest route between two points in florida
@app.get("/api/route")
def get_planned_route(
    start_lon: float = -81.3792,
    start_lat: float = 28.5383,
    goal_lon: float = -82.4572,
    goal_lat: float = 27.9506,
    mode: str = "simulated",
    time_step_hours: float = 0.0,
    danger_weight: float = 1.5,
):
    provider = _get_weather_provider(mode)
    config = RouteConfig(time_step_hours=time_step_hours, danger_weight=danger_weight)

    try:
        return find_safest_route(
            airspace_grid=airspace_grid,
            weather_provider=provider,
            start=(start_lon, start_lat),
            goal=(goal_lon, goal_lat),
            config=config,
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error))
