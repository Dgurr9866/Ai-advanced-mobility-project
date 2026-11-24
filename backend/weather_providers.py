from abc import ABC, abstractmethod
from geo_utils import haversine_miles, FLORIDA_BOUNDS
import math
import requests
import numpy as np
from scipy.interpolate import RegularGridInterpolator


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
    

#simulates florida weather for easy training 
class SimulatedFloridaWeather(BaseWeatherProvider):
    def __init__(
        self,
        base_wind_speed_mph: float = 12.0,
        base_wind_direction_degrees: float = 110.0,  # Typical SE Florida sea breeze
        storms: list = None,
    ):
        self.base_wind_speed_mph = base_wind_speed_mph
        self.base_wind_direction_degrees = base_wind_direction_degrees
        # Each storm is a dict defining start position, velocity (deg/hr), radius (miles), and peak intensity
        self.storms = storms or []

    @classmethod
    def generate_random_scenario(cls, num_storms: int = 10):
        """Spawns random moving thunderstorms inside Florida's bounding box."""
        storms = []
        for _ in range(num_storms):
            storms.append(
                {
                    #these values must be changed to avoid all the storms only in the oceans
                    "start_longitude": np.random.uniform(-87.5, -80.1),
                    "start_latitude": np.random.uniform(25.2, 30.8),

                    "velocity_longitude_per_hour": np.random.uniform(-0.15, 0.25),
                    "velocity_latitude_per_hour": np.random.uniform(-0.15, 0.25),
                    "radius_miles": np.random.uniform(12.0, 35.0),
                    "peak_wind_mph": np.random.uniform(35.0, 60.0),
                    "peak_rain_inches_per_hour": np.random.uniform(0.8, 2.2),
                }
            )

        #retruns the storms with a random base wind speed and direction
        return cls(
            base_wind_speed_mph=np.random.uniform(5.0, 18.0),
            base_wind_direction_degrees=np.random.uniform(0.0, 360.0),
            storms=storms,
        )

    #inside a grid gets the weather returning the windspeed, direction, and rain
    def get_weather_at(
        self, longitude: float, latitude: float, time_step_hours: float = 0.0
    ) -> dict:
        wind_speed_mph = self.base_wind_speed_mph
        wind_direction_degrees = self.base_wind_direction_degrees
        rain_inches_per_hour = 0.0

        for storm in self.storms:
            # Move storm center forward in time
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

            # Gaussian falloff from storm center
            if distance_miles < storm["radius_miles"] * 2.0:
                intensity = math.exp(
                    -0.5 * (distance_miles / (storm["radius_miles"] * 0.5)) ** 2
                )
                wind_speed_mph += (storm["peak_wind_mph"] - self.base_wind_speed_mph) * intensity
                rain_inches_per_hour += storm["peak_rain_inches_per_hour"] * intensity

                # Add rotational gust shift near storm core
                wind_direction_degrees = (wind_direction_degrees + 45.0 * intensity) % 360

        return {
            "wind_speed_mph": float(wind_speed_mph),
            "wind_direction_degrees": float(wind_direction_degrees),
            "rain_inches_per_hour": float(rain_inches_per_hour),
        }



class LiveFloridaWeather(BaseWeatherProvider):
    def __init__(self, grid_spacing_degrees: float = 0.5):
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
            "latitude": ",".join(f"{lat:.4f}" for lat in flat_latitudes),
            "longitude": ",".join(f"{lon:.4f}" for lon in flat_longitudes),
            "hourly": "wind_speed_80m,wind_direction_80m,precipitation",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_hours": 6,
            "timezone": "America/New_York",
        }

        response = requests.get(url, params=params, timeout=15)
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