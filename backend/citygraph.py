from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2

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
        distance = calculate_distance(
            self.cities[city1],
            self.cities[city2]
        )

        # Add connections in both directions.
        self.edges[city1][city2] = distance
        self.edges[city2][city1] = distance     
        
# Calculate the straight-line distance between two cities in miles.
def calculate_distance(city1: City, city2: City) -> float:
    lat1 = radians(city1.latitude)
    lon1 = radians(city1.longitude)

    lat2 = radians(city2.latitude)
    lon2 = radians(city2.longitude)

    # Calculate the differences in latitude and longitude.
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    
    # Calculate the Haversine value.
    a = sin(delta_lat / 2)**2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2)**2
    
    # Calculate the central angle between the two cities.
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    # Earth's approximate radius in miles.
    earth_radius = 3958.8

    # Return the distance in miles.
    return earth_radius * c

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