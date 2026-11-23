from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from weather_providers import SimulatedFloridaWeather, LiveFloridaWeather, export_weather_grid_geojson

app = FastAPI()

# Allow your Vite dev server (usually localhost:5173) to fetch data
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

simulated_weather = SimulatedFloridaWeather.generate_random_scenario(num_storms=5)
live_weather = None  # Lazy-load when user toggles "Live" mode


@app.get("/api/weather")
def get_weather_layer(mode: str = "simulated", time_step_hours: float = 0.0):
    global live_weather
    if mode == "live":
        if live_weather is None:
            live_weather = LiveFloridaWeather()
        provider = live_weather
    else:
        provider = simulated_weather

    return export_weather_grid_geojson(provider, time_step_hours=time_step_hours)