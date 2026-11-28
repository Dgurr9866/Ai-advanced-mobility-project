from abc import ABC, abstractmethod
import requests
import json
import math
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from geo_utils import haversine_miles, FLORIDA_BOUNDS, FLORIDA_GEOJSON_PATH


#an abstract slass that implements the function that all weather will use (simulated or real)
class BaseWeatherProvider(ABC):
    @abstractmethod
    def get_weather_at(
        self, longitude: float, latitude: float, time_step_hours: float = 0.0
    ) -> dict:
        """
        Must return:
        {
            "wind_speed_mph": float,
            "wind_direction_degrees": float,
            "rain_inches_per_hour": float,
        }
        """
        pass
    @abstractmethod
    def get_weather_batch(
          self, longitudes: np.ndarray, latitudes: np.ndarray, time_step_hours: float = 0.0
      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pass

#simulates florida weather for easy training 
def _generate_3d_fractal_noise(
    shape_3d: tuple[int, int, int],
    octaves: list[tuple[float, float]] = ((4.0, 0.65), (1.8, 0.35)),
    seed: int = None,
) -> np.ndarray:
    """
    Generates smooth, zero-mean, unit-variance 3D Perlin-style fractal noise
    over (time, latitude, longitude) using multi-scale Gaussian-filtered fields.
    """
    rng = np.random.default_rng(seed)
    combined = np.zeros(shape_3d, dtype=np.float64)

    for sigma, weight in octaves:
        raw = rng.standard_normal(shape_3d)
        # Smooth more strongly along time (axis 0) so weather evolves gradually
        smoothed = gaussian_filter(raw, sigma=(sigma * 0.6, sigma, sigma), mode="nearest")
        std = np.std(smoothed)
        if std > 1e-8:
            smoothed /= std
        combined += weight * smoothed

    combined /= np.std(combined) + 1e-8
    return combined


class SimulatedFloridaWeather(BaseWeatherProvider):
    def __init__(
        self,
        base_wind_speed_mph: float = 12.0,
        base_wind_direction_degrees: float = 110.0,
        storms: list = None,
        seed: int = None,
    ):
        self.base_wind_speed_mph = base_wind_speed_mph
        self.base_wind_direction_degrees = base_wind_direction_degrees
        self.storms = storms or []

        #the time needs to be in this window or the weather will be extreme
        # Build a 3D (time, latitude, longitude) noise grid covering Florida + 12-hour window
        self.noise_times = np.linspace(0.0, 12.0, 25)  # Every 0.5 hours
        self.noise_latitudes = np.linspace(
            FLORIDA_BOUNDS["min_latitude"], FLORIDA_BOUNDS["max_latitude"], 56
        )
        self.noise_longitudes = np.linspace(
            FLORIDA_BOUNDS["min_longitude"], FLORIDA_BOUNDS["max_longitude"], 64
        )
        grid_shape = (
            len(self.noise_times),
            len(self.noise_latitudes),
            len(self.noise_longitudes),
        )
        axes = (self.noise_times, self.noise_latitudes, self.noise_longitudes)

        speed_field = _generate_3d_fractal_noise(grid_shape, seed=seed)
        angle_field = _generate_3d_fractal_noise(
            grid_shape, seed=None if seed is None else seed + 1
        )
        moisture_field = _generate_3d_fractal_noise(
            grid_shape, seed=None if seed is None else seed + 2
        )

        self.speed_noise_interp = RegularGridInterpolator(
            axes, speed_field, bounds_error=False, fill_value=None
        )
        self.angle_noise_interp = RegularGridInterpolator(
            axes, angle_field, bounds_error=False, fill_value=None
        )
        self.moisture_noise_interp = RegularGridInterpolator(
            axes, moisture_field, bounds_error=False, fill_value=None
        )

    @classmethod
    def generate_random_scenario(
        cls,
        num_storms: int = 6,
        florida_geojson_path: str = str(FLORIDA_GEOJSON_PATH),
        seed: int = None,
    ):
        """Spawns random moving thunderstorms strictly inside Florida's landmass polygon."""
        rng = np.random.default_rng(seed)

        with open(florida_geojson_path, "r") as file:
            florida_data = json.load(file)
        florida_landmass = unary_union(
            [shape(feature["geometry"]) for feature in florida_data["features"]]
        )
        prepared_florida = prep(florida_landmass)
        min_lon, min_lat, max_lon, max_lat = florida_landmass.bounds

        storms = []
        attempts = 0
        while len(storms) < num_storms and attempts < num_storms * 50:
            attempts += 1
            candidate_lon = float(rng.uniform(min_lon, max_lon))
            candidate_lat = float(rng.uniform(min_lat, max_lat))

            # Reject points in the Gulf of Mexico or Atlantic Ocean
            if not prepared_florida.contains(Point(candidate_lon, candidate_lat)):
                continue

            storms.append(
                {
                    "start_longitude": candidate_lon,
                    "start_latitude": candidate_lat,
                    "velocity_longitude_per_hour": float(rng.uniform(-0.12, 0.20)),
                    "velocity_latitude_per_hour": float(rng.uniform(-0.12, 0.20)),
                    "radius_miles": float(rng.uniform(14.0, 32.0)),
                    "peak_wind_mph": float(rng.uniform(36.0, 58.0)),
                    "peak_rain_inches_per_hour": float(rng.uniform(0.8, 2.2)),
                }
            )

        return cls(
            base_wind_speed_mph=float(rng.uniform(8.0, 16.0)),
            base_wind_direction_degrees=float(rng.uniform(0.0, 360.0)),
            storms=storms,
            seed=seed,
        )

    def get_weather_batch(
      self, longitudes: np.ndarray, latitudes: np.ndarray, time_step_hours: float = 0.0
  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        clamped_time = float(np.clip(time_step_hours, self.noise_times[0], self.noise_times[-1]))
        times = np.full_like(longitudes, clamped_time)

        times = np.full_like(longitudes, time_step_hours)
        query = np.column_stack([times, latitudes, longitudes])

        wind_speeds = np.maximum(2.0, self.base_wind_speed_mph + self.speed_noise_interp(query) * 5.5)
        wind_dirs = (self.base_wind_direction_degrees + self.angle_noise_interp(query) * 35.0) % 360.0
        rains = np.maximum(0.0, (self.moisture_noise_interp(query) - 0.85) * 0.22)

        for storm in self.storms:
            s_lon = storm["start_longitude"] + storm["velocity_longitude_per_hour"] * time_step_hours
            s_lat = storm["start_latitude"] + storm["velocity_latitude_per_hour"] * time_step_hours

            # Vectorized Haversine across all cells at once
            dlat = np.radians(latitudes - s_lat)
            dlon = np.radians(longitudes - s_lon)
            a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(s_lat)) * np.cos(np.radians(latitudes)) * np.sin(dlon / 2) ** 2
            dist_miles = 2 * 3958.8 * np.arcsin(np.sqrt(a))

            mask = dist_miles < storm["radius_miles"] * 2.0
            if np.any(mask):
                intensity = np.exp(-0.5 * (dist_miles[mask] / (storm["radius_miles"] * 0.5)) ** 2)
                wind_speeds[mask] += np.maximum(0.0, (storm["peak_wind_mph"] - wind_speeds[mask]) * intensity)
                rains[mask] += storm["peak_rain_inches_per_hour"] * intensity
                wind_dirs[mask] = (wind_dirs[mask] + 45.0 * intensity) % 360.0

        return wind_speeds, wind_dirs, rains

    def get_weather_at(
        self, longitude: float, latitude: float, time_step_hours: float = 0.0
    ) -> dict:
        clamped_time = float(np.clip(time_step_hours, self.noise_times[0], self.noise_times[-1]))
        query = np.array([[clamped_time, latitude, longitude]])
        # query = np.array([[time_step_hours, latitude, longitude]])

        # 1. Underlying Perlin-style wind & moisture field across all of Florida
        speed_noise = float(self.speed_noise_interp(query)[0])
        angle_noise = float(self.angle_noise_interp(query)[0])
        moisture_noise = float(self.moisture_noise_interp(query)[0])

        wind_speed_mph = max(2.0, self.base_wind_speed_mph + speed_noise * 5.5)
        wind_direction_degrees = (
            self.base_wind_direction_degrees + angle_noise * 35.0
        ) % 360.0

        # Broad light-rain / drizzle bands where moisture_noise > 0.85
        rain_inches_per_hour = max(0.0, (moisture_noise - 0.85) * 0.22)

        # 2. Layer localized severe storm cells on top of the underlying field
        for storm in self.storms:
            current_storm_longitude = (
                storm["start_longitude"]
                + storm["velocity_longitude_per_hour"] * time_step_hours
            )
            current_storm_latitude = (
                storm["start_latitude"]
                + storm["velocity_latitude_per_hour"] * time_step_hours
            )

            distance_miles = haversine_miles(
                longitude, latitude, current_storm_longitude, current_storm_latitude
            )

            if distance_miles < storm["radius_miles"] * 2.0:
                intensity = math.exp(
                    -0.5 * (distance_miles / (storm["radius_miles"] * 0.5)) ** 2
                )
                wind_speed_mph += max(
                    0.0, (storm["peak_wind_mph"] - wind_speed_mph) * intensity
                )
                rain_inches_per_hour += storm["peak_rain_inches_per_hour"] * intensity
                wind_direction_degrees = (
                    wind_direction_degrees + 45.0 * intensity
                ) % 360.0

        return {
            "wind_speed_mph": float(wind_speed_mph),
            "wind_direction_degrees": float(wind_direction_degrees),
            "rain_inches_per_hour": float(rain_inches_per_hour),
        }



class LiveFloridaWeather(BaseWeatherProvider):
    def __init__(self, grid_spacing_degrees: float = 0.8):
        # 0.5° (~35 miles) = ~210 points total (well within Open-Meteo limits)
        #set thes values to the florida bounds to get the weather for the entire state
        self.grid_longitudes = np.arange(FLORIDA_BOUNDS["min_longitude"], FLORIDA_BOUNDS["max_longitude"], grid_spacing_degrees)
        self.grid_latitudes = np.arange(FLORIDA_BOUNDS["min_latitude"], FLORIDA_BOUNDS["max_latitude"], grid_spacing_degrees)

        mesh_longitude, mesh_latitude = np.meshgrid(
            self.grid_longitudes, self.grid_latitudes
        )
        self._fetch_and_build_interpolators(
            mesh_longitude.ravel(), mesh_latitude.ravel()
        )

    def _fetch_and_build_interpolators(
        self, flat_longitudes: np.ndarray, flat_latitudes: np.ndarray
    ):
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": ",".join(f"{lat:.3f}" for lat in flat_latitudes),
            "longitude": ",".join(f"{lon:.3f}" for lon in flat_longitudes),
            "hourly": "wind_speed_80m,wind_direction_80m,precipitation",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_hours": 6,
            "timezone": "America/New_York",
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        grid_shape = (len(self.grid_latitudes), len(self.grid_longitudes))
        axes = (self.grid_latitudes, self.grid_longitudes)

        self.wind_speed_interpolators = []
        self.wind_direction_u_interpolators = []
        self.wind_direction_v_interpolators = []
        self.rain_interpolators = []

        num_hours = len(data[0]["hourly"]["wind_speed_80m"])

        for hour_index in range(num_hours):
            wind_speeds = np.array(
                [item["hourly"]["wind_speed_80m"][hour_index] for item in data],
                dtype=float,
            ).reshape(grid_shape)

            wind_directions_rad = np.radians(
                [item["hourly"]["wind_direction_80m"][hour_index] for item in data]
            )
            wind_u = np.cos(wind_directions_rad).reshape(grid_shape)
            wind_v = np.sin(wind_directions_rad).reshape(grid_shape)

            rain_values = np.array(
                [item["hourly"]["precipitation"][hour_index] for item in data],
                dtype=float,
            ).reshape(grid_shape)

            self.wind_speed_interpolators.append(
                RegularGridInterpolator(axes, wind_speeds, bounds_error=False, fill_value=None)
            )
            self.wind_direction_u_interpolators.append(
                RegularGridInterpolator(axes, wind_u, bounds_error=False, fill_value=None)
            )
            self.wind_direction_v_interpolators.append(
                RegularGridInterpolator(axes, wind_v, bounds_error=False, fill_value=None)
            )
            self.rain_interpolators.append(
                RegularGridInterpolator(axes, rain_values, bounds_error=False, fill_value=None)
            )

    def get_weather_batch(
      self, longitudes: np.ndarray, latitudes: np.ndarray, time_step_hours: float = 0.0
  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
      hour_index = min(max(int(round(time_step_hours)), 0), len(self.wind_speed_interpolators) - 1)
      query = np.column_stack([latitudes, longitudes])

      wind_speeds = np.maximum(0.0, self.wind_speed_interpolators[hour_index](query))
      wind_u = self.wind_direction_u_interpolators[hour_index](query)
      wind_v = self.wind_direction_v_interpolators[hour_index](query)
      rains = np.maximum(0.0, self.rain_interpolators[hour_index](query))
      wind_dirs = (np.degrees(np.arctan2(wind_v, wind_u)) + 360.0) % 360.0

      return wind_speeds, wind_dirs, rains

    def get_weather_at(
        self, longitude: float, latitude: float, time_step_hours: float = 0.0
    ) -> dict:
        hour_index = min(
            max(int(round(time_step_hours)), 0),
            len(self.wind_speed_interpolators) - 1,
        )
        # RegularGridInterpolator expects (latitude, longitude) order to match `axes`
        query_point = np.array([[latitude, longitude]])

        wind_speed = float(self.wind_speed_interpolators[hour_index](query_point)[0])
        wind_u = float(self.wind_direction_u_interpolators[hour_index](query_point)[0])
        wind_v = float(self.wind_direction_v_interpolators[hour_index](query_point)[0])
        rain = float(self.rain_interpolators[hour_index](query_point)[0])

        wind_direction_degrees = (math.degrees(math.atan2(wind_v, wind_u)) + 360) % 360

        return {
            "wind_speed_mph": max(wind_speed, 0.0),
            "wind_direction_degrees": wind_direction_degrees,
            "rain_inches_per_hour": max(rain, 0.0),
        }