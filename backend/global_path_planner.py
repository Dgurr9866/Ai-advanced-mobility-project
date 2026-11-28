# backend/global_path_planner.py
import heapq
from dataclasses import dataclass
from florida_map_grid import FloridaAirspaceGrid
from geo_utils import distance_and_bearing_miles, haversine_miles

GridIndex = tuple[int, int]
CoordPair = tuple[float, float]

danger_thresholds = {
    "safe": 5.0,
    "moderate": 15.0,
    "high": 40.0,
    "crash_zone": 500.0,
}


@dataclass(frozen=True)
class RouteConfig:
    time_step_hours: float = 0.0
    drone_speed_mph: float = 45.0
    payload_ratio: float = 0.5
    danger_weight: float = 1.5
    avoid_crash_zones: bool = True


def _cell_coords(grid: FloridaAirspaceGrid, idx: GridIndex) -> CoordPair:
    cell = grid.cells[idx]
    return cell["longitude"], cell["latitude"]


def _edge_cost(
    grid: FloridaAirspaceGrid,
    weather_provider,
    from_idx: GridIndex,
    to_idx: GridIndex,
    current_time_hours: float,
    config: RouteConfig,
) -> tuple[float, float]:
    """
    Calculates (step_cost, step_miles) between two adjacent cells.
    Returns (inf, 0.0) if the target cell is an impassable crash zone.
    """
    from_lon, from_lat = _cell_coords(grid, from_idx)
    to_lon, to_lat = _cell_coords(grid, to_idx)

    step_miles, heading_deg = distance_and_bearing_miles(from_lon, from_lat, to_lon, to_lat)
    danger = grid.calculate_cell_danger(
        grid_index=to_idx,
        weather_provider=weather_provider,
        time_step_hours=current_time_hours,
        heading_degrees=heading_deg,
        drone_payload_ratio=config.payload_ratio,
    )

    if config.avoid_crash_zones and danger >= danger_thresholds["crash_zone"]:
        return float("inf"), 0.0

    danger_multiplier = 1.0 + config.danger_weight * (danger / 15.0)
    return step_miles * danger_multiplier, step_miles


def _unwrap_path(came_from: dict[GridIndex, GridIndex], goal_idx: GridIndex) -> list[GridIndex]:
    path = [goal_idx]
    while path[-1] in came_from:
        path.append(came_from[path[-1]])
    path.reverse()
    return path


def _build_route_geojson(
    grid: FloridaAirspaceGrid,
    weather_provider,
    path_indices: list[GridIndex],
    start_coords: CoordPair,
    goal_coords: CoordPair,
    config: RouteConfig,
) -> dict:
    """Converts ordered grid indices into a MapLibre LineString GeoJSON with flight stats."""
    waypoints = [list(start_coords)]
    waypoints.extend(list(_cell_coords(grid, idx)) for idx in path_indices)
    waypoints.append(list(goal_coords))

    total_miles = 0.0
    max_danger = 0.0
    danger_sum = 0.0
    sim_time = config.time_step_hours
    speed = max(config.drone_speed_mph, 1.0)

    time_checkpoints = []
    next_checkpoint_hour = config.time_step_hours + 1.0

    for i, idx in enumerate(path_indices):
        heading = None
        curr_lon, curr_lat = _cell_coords(grid, idx)

        if i > 0:
            prev_lon, prev_lat = _cell_coords(grid, path_indices[i - 1])
            seg_miles, heading = distance_and_bearing_miles(prev_lon, prev_lat, curr_lon, curr_lat)
            total_miles += seg_miles
            sim_time += seg_miles / speed

        danger = grid.calculate_cell_danger(
            grid_index=idx,
            weather_provider=weather_provider,
            time_step_hours=sim_time,
            heading_degrees=heading,
            drone_payload_ratio=config.payload_ratio,
        )
        max_danger = max(max_danger, danger)
        danger_sum += danger

        # Record a checkpoint every ~1.0 hour of flight and at the final waypoint
        is_last = i == len(path_indices) - 1
        if sim_time >= next_checkpoint_hour or is_last:
            time_checkpoints.append({
                "time_hours": round(sim_time, 1),
                "coordinates": [round(curr_lon, 5), round(curr_lat, 5)],
                "danger": round(danger, 1),
            })
            next_checkpoint_hour = sim_time + 1.0

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": waypoints,
        },
        "properties": {
            "distance_miles": round(total_miles, 2),
            "estimated_flight_hours": round(total_miles / speed, 2),
            "average_danger": round(danger_sum / max(len(path_indices), 1), 2),
            "max_danger": round(max_danger, 2),
            "waypoint_count": len(waypoints),
            "route_type": "astar_safe",
            "time_checkpoints": time_checkpoints,
        },
    }

def find_safest_route(
    airspace_grid: FloridaAirspaceGrid,
    weather_provider,
    start: CoordPair,
    goal: CoordPair,
    config: RouteConfig = RouteConfig(),
) -> dict:
    """Runs A* across FloridaAirspaceGrid and returns a GeoJSON LineString route."""
    start_idx = airspace_grid.snap_coordinate_to_grid(*start)
    goal_idx = airspace_grid.snap_coordinate_to_grid(*goal)

    if start_idx is None or goal_idx is None:
        raise ValueError("Start or goal is outside valid Florida airspace.")

    goal_lon, goal_lat = _cell_coords(airspace_grid, goal_idx)
    speed = max(config.drone_speed_mph, 1.0)

    open_heap: list[tuple[float, int, GridIndex]] = [(0.0, 0, start_idx)]
    came_from: dict[GridIndex, GridIndex] = {}
    g_score: dict[GridIndex, float] = {start_idx: 0.0}
    arrival_time: dict[GridIndex, float] = {start_idx: config.time_step_hours}
    visited: set[GridIndex] = set()
    tie_breaker = 0

    while open_heap:
        _, _, current_idx = heapq.heappop(open_heap)

        if current_idx == goal_idx:
            path_indices = _unwrap_path(came_from, goal_idx)
            return _build_route_geojson(
                airspace_grid, weather_provider, path_indices, start, goal, config
            )

        if current_idx in visited:
            continue
        visited.add(current_idx)

        curr_time = arrival_time[current_idx]

        for neighbor_idx in airspace_grid.get_neighbors(current_idx):
            if neighbor_idx in visited:
                continue

            step_cost, step_miles = _edge_cost(
                airspace_grid, weather_provider, current_idx, neighbor_idx, curr_time, config
            )
            if step_cost == float("inf"):
                continue

            tentative_g = g_score[current_idx] + step_cost
            if tentative_g >= g_score.get(neighbor_idx, float("inf")):
                continue

            came_from[neighbor_idx] = current_idx
            g_score[neighbor_idx] = tentative_g
            arrival_time[neighbor_idx] = curr_time + (step_miles / speed)

            nbr_lon, nbr_lat = _cell_coords(airspace_grid, neighbor_idx)
            heuristic = haversine_miles(nbr_lon, nbr_lat, goal_lon, goal_lat)

            tie_breaker += 1
            heapq.heappush(open_heap, (tentative_g + heuristic, tie_breaker, neighbor_idx))

    raise RuntimeError("No safe route found without entering a crash zone.")