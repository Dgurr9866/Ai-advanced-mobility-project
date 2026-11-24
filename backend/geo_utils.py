# backend/geo_utils.py
import math
from pathlib import Path

"""
Shared geographic constants and utility functions for the project.
This was made to avoid code duplication and inconsistencies in implementations
"""

# --- Shared Project Paths ---
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "frontend" / "public" / "data"

FLORIDA_GEOJSON_PATH = DATA_DIR / "florida.geojson"
NO_FLY_ZONES_GEOJSON_PATH = DATA_DIR / "no_fly_zones.geojson"

# --- Shared Geographic Constants ---
EARTH_RADIUS_MILES = 3958.8
FLORIDA_BOUNDS = {
    "min_lon": -87.7,
    "max_lon": -79.8,
    "min_lat": 24.5,
    "max_lat": 31.2,
    "avg_lat": 28.0,
}


def miles_to_degree_steps(cell_size_miles: float) -> tuple[float, float]:
    """Converts a uniform mile spacing into (longitude_step_deg, latitude_step_deg) at FL's latitude."""
    latitude_step_deg = cell_size_miles / 69.0
    longitude_step_deg = cell_size_miles / (
        69.0 * math.cos(math.radians(FLORIDA_BOUNDS["avg_lat"]))
    )
    return longitude_step_deg, latitude_step_deg


def haversine_miles(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    """Calculates great-circle distance in miles between two (longitude, latitude) points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def distance_and_bearing_miles(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> tuple[float, float]:
    """Returns (distance_miles, initial_bearing_degrees_clockwise_from_north)."""
    distance_miles = haversine_miles(lon1, lat1, lon2, lat2)

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing_degrees = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

    return distance_miles, bearing_degrees


def calculate_headwind_mph(
    wind_speed_mph: float, wind_direction_degrees: float, travel_heading_degrees: float
) -> float:
    """Returns positive headwind (or negative tailwind) in mph along travel_heading_degrees."""
    angle_diff = math.radians(wind_direction_degrees - travel_heading_degrees)
    return wind_speed_mph * math.cos(angle_diff)