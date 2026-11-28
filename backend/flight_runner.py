# backend/flight_runner.py
import uuid
from drone import Drone
from florida_map_grid import FloridaAirspaceGrid
from global_path_planner import RouteConfig, find_safest_route

CoordPair = tuple[float, float]


class FlightRunner:
    """Handles pre-flight A* planning and baseline step-by-step Drone simulation."""

    def __init__(self, grid: FloridaAirspaceGrid):
        self.grid = grid
        self.planned_flights: dict[str, dict] = {}

    #plans flight accounting for battery usage and weather conditions, returns a flight plan with a unique flight id
    def plan_flight(
        self,
        weather_provider,
        start: CoordPair,
        goal: CoordPair,
        time_step_hours: float = 0.0,
        payload_ratio: float = 0.5,
    ) -> dict:
        """Computes an A* route and estimates battery usage for pre-flight approval."""
        route_geojson = find_safest_route(
            airspace_grid=self.grid,
            weather_provider=weather_provider,
            start=start,
            goal=goal,
            config=RouteConfig(
                time_step_hours=time_step_hours,
                payload_ratio=payload_ratio,
            ),
        )

        # Use Drone's own battery math for the pre-flight estimate
        preview_drone = Drone(
            longitude=start[0],
            latitude=start[1],
            payload_ratio=payload_ratio,
            sim_time_hours=time_step_hours,
        )
        distance_miles = route_geojson["properties"]["distance_miles"]
        est_burn = preview_drone.estimate_battery_burn(distance_miles)

        flight_id = str(uuid.uuid4())[:8]
        plan = {
            "flight_id": flight_id,
            "start": list(start),
            "goal": list(goal),
            "time_step_hours": time_step_hours,
            "payload_ratio": payload_ratio,
            "route_geojson": route_geojson,
            "summary": {
                "distance_miles": distance_miles,
                "estimated_arrival_battery": round(100.0 - est_burn, 1),
                "max_danger": route_geojson["properties"]["max_danger"],
            },
        }
        self.planned_flights[flight_id] = plan
        return plan

    #directly follows the planned flight with no avoidance
    def run_flight(
        self,
        flight_id: str,
        weather_provider,
        max_steps: int = 500,
    ) -> dict:
        """Flies a Drone instance step-by-step along the approved A* waypoints."""
        plan = self.planned_flights.get(flight_id)
        if plan is None:
            raise KeyError(f"Flight '{flight_id}' not found.")

        waypoints = plan["route_geojson"]["geometry"]["coordinates"]
        drone = Drone(
            longitude=plan["start"][0],
            latitude=plan["start"][1],
            payload_ratio=plan["payload_ratio"],
            sim_time_hours=plan["time_step_hours"],
        )

        waypoint_idx = 1
        for _ in range(max_steps):
            if drone.status == "CRASHED":
                break
            if waypoint_idx >= len(waypoints):
                drone.status = "ARRIVED"
                drone.status_reason = "Reached destination safely."
                break

            target_lon, target_lat = waypoints[waypoint_idx]
            reached = drone.step_towards(target_lon, target_lat, weather_provider)
            if reached:
                waypoint_idx += 1

        return {
            "flight_id": flight_id,
            "route_geojson": plan["route_geojson"],
            "drone": drone.to_dict(),
        }