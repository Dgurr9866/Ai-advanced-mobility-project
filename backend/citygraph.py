from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2
from geo_utils import haversine_miles

#give dataclass decorator for creating data classes
@dataclass
class City:
    name: str
    latitude: float
    longitude: float

# Represents our network of Florida cities.
class CityGraph:
    def __init__(self):
        # Store cities by name.
        self.cities: dict[str, City] = {}

        # Store connections and their distances in miles.
        self.edges: dict[str, dict[str, float]] = {}
    # Add a city as a vertex in the graph.
    def add_city(self, city: City) -> None:
        self.cities[city.name] = city
        self.edges[city.name] = {}
        
    # Connect two cities with an undirected, weighted edge.
    def add_edge(self, city1: str, city2: str) -> None:
        # Calculate the distance between the cities in miles.
        distance = haversine_miles(
            self.cities[city1].longitude,
            self.cities[city1].latitude,
            self.cities[city2].longitude,
            self.cities[city2].latitude
        )

        # Add connections in both directions.
        self.edges[city1][city2] = distance
        self.edges[city2][city1] = distance     

if __name__ == "__main__":
    tampa = City("Tampa", 27.9506, -82.4572)
    print(tampa)
    orlando = City("Orlando", 28.5383, -81.3792)

    # Creategraph.
    graph = CityGraph()

    # Add two cities as vertices.
    graph.add_city(tampa)
    graph.add_city(orlando)

    # Connect Tampa and Orlando.
    graph.add_edge("Tampa", "Orlando")

    # Display the adjacency list.
    print(graph.edges)