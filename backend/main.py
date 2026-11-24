from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from citygraph import City, calculate_distance


app = FastAPI(title="Florida Drone Safety Simulator")

# Allow the local React frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "message": "Florida Drone Safety Simulator API"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}



@app.get("/routes/test")
def test_route():

    # Create two Florida cities
    orlando = City("Orlando", 28.5383, -81.3792)
    tampa = City("Tampa", 27.9506, -82.4572)

    # Calculate straight-line distance in miles
    distance = calculate_distance(orlando, tampa)

    # Return a GeoJSON feature for MapLibre
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [orlando.longitude, orlando.latitude],
                [tampa.longitude, tampa.latitude]
            ]
        },
        "properties": {
            "origin": orlando.name,
            "destination": tampa.name,
            "distance_miles": round(distance, 2),
            "route_type": "test"
        }
    }
