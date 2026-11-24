import math
import numpy as np
from geo_utils import haversine_miles, distance_and_bearing_miles

class Drone:
    def __init__(
        self,
        longitude: float,
        latitude: float,
        max_weight: float,
        current_weight: float,
        max_speed: float,
        current_speed: float = 0.0,
        battery_percent: float = 100.0,
    ):
        self.longitude = longitude
        self.latitude = latitude
        self.max_weight = max_weight
        self.current_weight = current_weight
        self.max_speed = max_speed
        self.current_speed = current_speed
        self.battery_percent = battery_percent
        
        # Track flight history so you can export the flown path back to GeoJSON
        self.path_history = [(longitude, latitude)] # Will be a list of points on the map that make the path
        self.crashed = False
        self.crash_reason = None

    @property
    def payload_ratio(self) -> float:
        return self.current_weight / self.max_weight if self.max_weight > 0 else 0.0

    #then well need various functions to calculate things
    def max_distance(): #use current weight and battery percent 
        pass


    def get_ml_features(self, target_lon: float, target_lat: float, weather: dict) -> np.ndarray:
        """Returns a 1D feature row in imperial units for scikit-learn model.predict()."""
        dist_mi, bearing_deg = distance_and_bearing_miles(self.longitude, self.latitude, target_lon, target_lat)
        wind_angle_diff = math.radians(weather["wind_direction_degrees"] - bearing_deg)
        headwind_mph = weather["wind_speed_mph"] * math.cos(wind_angle_diff)

        return np.array([
            self.battery_percent,
            self.payload_ratio,
            dist_mi,
            bearing_deg,
            weather["wind_speed_mph"],
            headwind_mph,
            weather["rain_inches_per_hour"],
        ], dtype=np.float32)

    

    
