import json
import numpy as np
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from geo_utils import FLORIDA_BOUNDS, miles_to_degree_steps, calculate_headwind_mph


class FloridaAirspaceGrid:
    def __init__(
        self,
        florida_geojson_path: str,
        no_fly_zones_geojson_path: str = None,
        cell_size_miles: float = 5.0,
    ):
        self.cell_size_miles = cell_size_miles

        # 1. Load Florida landmass polygon(s)
        with open(florida_geojson_path, "r") as file:
            florida_data = json.load(file)

        florida_shapes = [
            shape(feature["geometry"]) for feature in florida_data["features"]
        ]
        florida_landmass = unary_union(florida_shapes)

        # 2. Load and subtract No-Fly Zones (airports, military bases, TFRs) if provided
        self.no_fly_union = None
        if no_fly_zones_geojson_path:
            with open(no_fly_zones_geojson_path, "r") as file:
                nfz_data = json.load(file)
            nfz_shapes = [
                shape(feature["geometry"]) for feature in nfz_data["features"]
            ]
            self.no_fly_union = unary_union(nfz_shapes)
            valid_airspace_polygon = florida_landmass.difference(self.no_fly_union)
        else:
            valid_airspace_polygon = florida_landmass

        # Prepare geometry for ultra-fast point-in-polygon checks
        prepared_airspace = prep(valid_airspace_polygon)

        # 3. Generate uniform mile-based grid and filter out Ocean + No-Fly Zones
        self.longitude_step, self.latitude_step = miles_to_degree_steps(cell_size_miles)

        longitudes = np.arange(FLORIDA_BOUNDS["min_longitude"], FLORIDA_BOUNDS["max_longitude"], self.longitude_step)
        latitudes = np.arange(FLORIDA_BOUNDS["min_latitude"], FLORIDA_BOUNDS["max_latitude"], self.latitude_step)
        self.cells = {}  # Maps (row_index, column_index) -> cell metadata dict

        for row_index, latitude in enumerate(latitudes):
            for column_index, longitude in enumerate(longitudes):
                point = Point(float(longitude), float(latitude))

                # Skip open ocean and no-fly zones completely
                if not prepared_airspace.contains(point):
                    continue

                # Static danger bonus if flying very close to a No-Fly Zone border
                nfz_proximity_danger = 0.0
                if self.no_fly_union is not None:
                    # Approx degrees to miles (~65 mi/deg in FL)
                    distance_to_nfz_miles = point.distance(self.no_fly_union) * 65.0
                    if distance_to_nfz_miles < 5.0:
                        nfz_proximity_danger = (5.0 - distance_to_nfz_miles) * 4.0

                self.cells[(row_index, column_index)] = {
                    "grid_index": (row_index, column_index),
                    "longitude": float(longitude),
                    "latitude": float(latitude),
                    "static_danger": nfz_proximity_danger,
                }

    def get_neighbors(self, grid_index: tuple) -> list:
        """Returns valid 8-connected neighbor grid indices (excludes ocean & NFZs)."""
        row_index, column_index = grid_index
        neighbors = []
        for delta_row in (-1, 0, 1):
            for delta_column in (-1, 0, 1):
                if delta_row == 0 and delta_column == 0:
                    continue
                neighbor_index = (row_index + delta_row, column_index + delta_column)
                if neighbor_index in self.cells:
                    neighbors.append(neighbor_index)
        return neighbors

    def snap_coordinate_to_grid(self, longitude: float, latitude: float) -> tuple:
        """Finds the nearest valid airspace cell index for a given (longitude, latitude)."""
        best_index = None
        best_distance_squared = float("inf")

        for grid_index, cell in self.cells.items():
            distance_squared = (cell["longitude"] - longitude) ** 2 + (
                cell["latitude"] - latitude
            ) ** 2
            if distance_squared < best_distance_squared:
                best_distance_squared = distance_squared
                best_index = grid_index

        return best_index

    def calculate_cell_danger(
        self,
        grid_index: tuple,
        weather_provider,
        time_step_hours: float = 0.0,
        heading_degrees: float = None,
        drone_payload_ratio: float = 0.5,
    ) -> float:
        """
        Computes a unified danger value for a cell:
        - 0.0 to ~15.0: Safe / low risk
        - 15.0 to 50.0: Moderate weather / headwind drag
        - 100.0+: Severe storm crash zone
        """
        cell = self.cells[grid_index]
        weather = weather_provider.get_weather_at(
            cell["longitude"], cell["latitude"], time_step_hours
        )

        wind_speed_mph = weather["wind_speed_mph"]
        rain_inches_per_hour = weather["rain_inches_per_hour"]

        # Base danger from static airspace proximity + wind + precipitation
        danger = cell["static_danger"]
        danger += (wind_speed_mph * 0.4) * (1.0 + 0.3 * drone_payload_ratio)
        danger += rain_inches_per_hour * 25.0

        # Add directional headwind penalty if travel heading is known (for Dijkstra/A* edges)
        if heading_degrees is not None:
            headwind_mph = calculate_headwind_mph(
                wind_speed_mph, weather["wind_direction_degrees"], heading_degrees
            )
            if headwind_mph > 0:
                danger += headwind_mph * 0.5

        # Massive spike if cell exceeds severe weather crash thresholds
        if wind_speed_mph > 40.0 or rain_inches_per_hour > 1.0:
            danger += 500.0

        return float(danger)

    def export_danger_grid_geojson(
        self, weather_provider, time_step_hours: float = 0.0
    ) -> dict:
        """
        Exports ONLY valid Florida airspace cells (no oceans, no NFZs) with their
        computed `danger_value` and weather properties for MapLibre rendering.
        """
        half_latitude = self.latitude_step / 2.0
        half_longitude = self.longitude_step / 2.0
        features = []

        for grid_index, cell in self.cells.items():
            longitude = cell["longitude"]
            latitude = cell["latitude"]
            weather = weather_provider.get_weather_at(
                longitude, latitude, time_step_hours
            )
            danger_value = self.calculate_cell_danger(
                grid_index, weather_provider, time_step_hours
            )

            polygon_coordinates = [[
                [longitude - half_longitude, latitude - half_latitude],
                [longitude + half_longitude, latitude - half_latitude],
                [longitude + half_longitude, latitude + half_latitude],
                [longitude - half_longitude, latitude + half_latitude],
                [longitude - half_longitude, latitude - half_latitude],
            ]]

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": polygon_coordinates,
                },
                "properties": {
                    "danger_value": round(danger_value, 1),
                    "wind_speed_mph": round(weather["wind_speed_mph"], 1),
                    "wind_direction_degrees": round(weather["wind_direction_degrees"], 1),
                    "rain_inches_per_hour": round(weather["rain_inches_per_hour"], 2),
                },
            })

        return {
            "type": "FeatureCollection",
            "features": features,
        }