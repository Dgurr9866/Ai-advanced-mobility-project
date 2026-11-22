import math
import numpy as np

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

    #then well need various functions to calculate things
    def max_distance(): #use current weight and battery percent 
        pass

    #calculates distance(km) and and bearing degrees to a target 
    def distance_and_bearing_to(self, target_longitude: float, target_latitude: float):
        """Returns approximate distance (miles) and bearing (degrees) to target."""
        earth_radius_miles = 3958.8
        latitude_1 = math.radians(self.latitude)
        longitude_1 = math.radians(self.longitude)
        latitude_2 = math.radians(target_latitude)
        longitude_2 = math.radians(target_longitude)

        delta_latitude = latitude_2 - latitude_1
        delta_longitude = longitude_2 - longitude_1

        haversine_a = math.sin(delta_latitude / 2) ** 2 + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(delta_longitude / 2) ** 2
        
        distance_miles = 2 * earth_radius_miles * math.asin(math.sqrt(haversine_a))

        y = math.sin(delta_longitude) * math.cos(latitude_2)
        x = math.cos(latitude_1) * math.sin(latitude_2) - math.sin(latitude_1) * math.cos(latitude_2) * math.cos(delta_longitude)
    
        bearing_degrees = (math.degrees(math.atan2(y, x)) + 360) % 360

        return distance_miles, bearing_degrees



    def get_ml_features(self, target_lon: float, target_lat: float, weather: dict) -> np.ndarray:
        """Returns a 1D feature row in imperial units for scikit-learn model.predict()."""
        dist_mi, bearing_deg = self.distance_and_bearing_to(target_lon, target_lat)
        wind_angle_diff = math.radians(weather["wind_dir_deg"] - bearing_deg)
        headwind_mph = weather["wind_speed_mph"] * math.cos(wind_angle_diff)

        return np.array([
            self.battery_percent,
            self.payload_ratio,
            dist_mi,
            bearing_deg,
            weather["wind_speed_mph"],
            headwind_mph,
            weather["rain_inh"],
        ], dtype=np.float32)

    

    
