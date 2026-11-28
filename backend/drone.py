# backend/drone.py
from dataclasses import dataclass, field
from typing import Literal
from geo_utils import calculate_headwind_mph, distance_and_bearing_miles

DroneStatus = Literal["IDLE", "IN_FLIGHT", "ARRIVED", "DIVERTED", "CRASHED"]


@dataclass
class Drone:
    longitude: float
    latitude: float
    battery_percent: float = 100.0
    payload_ratio: float = 0.5
    cruise_speed_mph: float = 45.0
    sim_time_hours: float = 0.0
    status: DroneStatus = "IDLE"
    status_reason: str = ""
    flown_trail: list[list[float]] = field(default_factory=list)
    telemetry_log: list[dict] = field(default_factory=list)

    # Physical & safety limits
    MAX_WIND_MPH: float = 40.0
    MAX_RAIN_IN_HR: float = 1.0
    BASE_BURN_PER_MILE: float = 0.20  # ~425 mi range at 50% payload

    def __post_init__(self):
        if not self.flown_trail:
            self.flown_trail.append([round(self.longitude, 5), round(self.latitude, 5)])

    #based off key factors calculates what the battery burn would be
    def estimate_battery_burn(
        self,
        distance_miles: float,
        speed_multiplier: float = 1.0,
        headwind_mph: float = 0.0,
        rain_in_hr: float = 0.0,
    ) -> float:
        """Calculates battery percentage consumed for a given leg."""
        aero_factor = speed_multiplier ** 2
        weather_drag = 1.0 + max(0.0, headwind_mph) * 0.015 + rain_in_hr * 0.4
        payload_factor = 1.0 + 0.35 * self.payload_ratio
        return distance_miles * self.BASE_BURN_PER_MILE * aero_factor * weather_drag * payload_factor

    #returns the features of the drone the the ml model will use for training and prediction
    def get_ml_features(
        self,
        target_lon: float,
        target_lat: float,
        weather_provider,
    ) -> list[float]:
        """Returns the 7-feature state vector used by both ML and RL models."""
        dist_mi, bearing_deg = distance_and_bearing_miles(
            self.longitude, self.latitude, target_lon, target_lat
        )
        weather = weather_provider.get_weather_at(
            self.longitude, self.latitude, self.sim_time_hours
        )
        wind_speed = weather["wind_speed_mph"]
        wind_dir = weather["wind_direction_degrees"]
        rain = weather["rain_inches_per_hour"]
        headwind = calculate_headwind_mph(wind_speed, wind_dir, bearing_deg)

        return [
            round(self.battery_percent, 2),
            round(self.payload_ratio, 2),
            round(dist_mi, 2),
            round(bearing_deg, 1),
            round(wind_speed, 2),
            round(headwind, 2),
            round(rain, 3),
        ]

    def step_towards(
        self,
        target_lon: float,
        target_lat: float,
        weather_provider,
        speed_multiplier: float = 1.0,
        step_minutes: float = 3.0,
        action_label: str = "CONTINUE",
    ) -> bool:
        """
        Advances the drone by one time step toward (target_lon, target_lat).
        Returns True if the target waypoint was reached on this step.
        """
        if self.status in ("CRASHED", "ARRIVED", "DIVERTED"):
            return False

        self.status = "IN_FLIGHT"
        dt_hours = step_minutes / 60.0

        #gets distance and bearing to the target, gets the weather at the current location
        dist_to_target, bearing = distance_and_bearing_miles(
            self.longitude, self.latitude, target_lon, target_lat
        )
        weather = weather_provider.get_weather_at(
            self.longitude, self.latitude, self.sim_time_hours
        )
        wind_speed = weather["wind_speed_mph"]
        rain = weather["rain_inches_per_hour"]
        headwind = calculate_headwind_mph(
            wind_speed, weather["wind_direction_degrees"], bearing
        )

        # Weather crash check
        if wind_speed > self.MAX_WIND_MPH or rain > self.MAX_RAIN_IN_HR:
            self.status = "CRASHED"
            self.status_reason = (
                f"Exceeded weather limits (wind {wind_speed:.1f} mph, rain {rain:.2f} in/hr)."
            )
            return False

        airspeed = self.cruise_speed_mph * speed_multiplier
        groundspeed = max(10.0, airspeed - 0.6 * headwind)
        step_miles = groundspeed * dt_hours

        #if its going farther than the distance to target its done
        reached_target = step_miles >= dist_to_target
        if reached_target:
            self.longitude, self.latitude = target_lon, target_lat
            actual_miles = dist_to_target
        else:
            fraction = step_miles / max(dist_to_target, 1e-6)
            self.longitude += (target_lon - self.longitude) * fraction
            self.latitude += (target_lat - self.latitude) * fraction
            actual_miles = step_miles

        #updates the battery and time, logs the telemetry, and checks if the battery is depleted
        actual_dt_hours = actual_miles / groundspeed
        burn = self.estimate_battery_burn(actual_miles, speed_multiplier, headwind, rain)
        self.battery_percent = max(0.0, self.battery_percent - burn)
        self.sim_time_hours += actual_dt_hours

        self.flown_trail.append([round(self.longitude, 5), round(self.latitude, 5)])
        self.telemetry_log.append({
            "time_hours": round(self.sim_time_hours, 2),
            "battery_percent": round(self.battery_percent, 1),
            "groundspeed_mph": round(groundspeed, 1),
            "wind_speed_mph": round(wind_speed, 1),
            "headwind_mph": round(headwind, 1),
            "action": action_label,
        })

        if self.battery_percent <= 0.0:
            self.status = "CRASHED"
            self.status_reason = "Battery depleted mid-flight."
            return False

        return reached_target

    def to_dict(self) -> dict:
        """Serializes current drone state and flown trail for API responses."""
        return {
            "position": [round(self.longitude, 5), round(self.latitude, 5)],
            "battery_percent": round(self.battery_percent, 1),
            "sim_time_hours": round(self.sim_time_hours, 2),
            "status": self.status,
            "status_reason": self.status_reason,
            "flown_trail_geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": self.flown_trail,
                },
                "properties": {"status": self.status},
            },
            "telemetry_log": self.telemetry_log,
        }