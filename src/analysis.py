import math
from typing import List, Dict, Any # Added for compatibility with older Python versions

# --- 1. CONFIGURATION & CONSTANTS ---

EDMONTON_BOUNDS = {
    "north": 53.72,
    "south": 53.38,
    "west": -113.72,
    "east": -113.28,
}

# polygon defintion for Edmonton city limits
EDMONTON_POLYGON = [
    [-113.71, 53.66], [-113.36, 53.66], [-113.36, 53.42],
    [-113.71, 53.42], [-113.71, 53.66]
]

CELL_SIZE_KM = 1.0

# --- 2. DATA STRUCTURES (Classes) ---

class Point:
    def __init__(self, lat: float, lng: float):
        self.lat = lat
        self.lng = lng

class Station:
    def __init__(self, id: str, location: Point):
        self.id = id
        self.location = location

class Incident:
    def __init__(self, id: str, location: Point):
        self.id = id
        self.location = location

class GridCell:
    def __init__(self, id: str, row: int, col: int, bounds: Dict[str, float]):
        self.id = id
        self.row = row
        self.col = col
        self.bounds = bounds
        self.incident_count = 0
        self.has_station = False
        self.distance_to_station = -1.0
        self.score = 0.0

    def __repr__(self):
        return f"Cell({self.id} | Score: {self.score:.2f} | Incidents: {self.incident_count} | Dist: {self.distance_to_station})"

# --- 3. HELPER FUNCTIONS ---

def calculate_grid_dimensions():
    """Calculats row and col counts based on Edmonton boundries."""
    lat_distance = (EDMONTON_BOUNDS["north"] - EDMONTON_BOUNDS["south"]) * 111320 # meters
    # Longitude distnce changes based on latitude (Cosine correction)
    avg_lat_rad = math.radians(EDMONTON_BOUNDS["south"])
    lng_distance = (EDMONTON_BOUNDS["east"] - EDMONTON_BOUNDS["west"]) * 111320 * math.cos(avg_lat_rad)
    
    rows = math.floor(lat_distance / (CELL_SIZE_KM * 1000))
    cols = math.floor(lng_distance / (CELL_SIZE_KM * 1000))
    return rows, cols, lat_distance, lng_distance

def is_point_in_polygon(point: Point, polygon: List[List[float]]) -> bool:
    """Checks if point is inside polygon using Ray-casting algo."""
    x, y = point.lng, point.lat
    inside = False
    j = len(polygon) - 1
    
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        
        intersect = ((yi > y) != (yj > y)) and \
                    (x < (xj - xi) * (y - yi) / (yj - yi + 1e-10) + xi) # epsilon to prevent div by zero
        if intersect:
            inside = not inside
        j = i
        
    return inside

def normalize(value: float, min_val: float, max_val: float) -> float:
    """Squeezes values betwen 0 and 1."""
    if max_val == min_val:
        return 1.0
    return (value - min_val) / (max_val - min_val)

def calculate_manhattan_distance(cell_a: GridCell, cell_b: GridCell) -> int:
    """Manhattan distance on grid (Row diff + Col diff)."""
    return abs(cell_a.row - cell_b.row) + abs(cell_a.col - cell_b.col)

def get_cell_from_coords(location: Point, cell_height: float, cell_width: float):
    """Converts cords to row and col numbers."""
    if (location.lat < EDMONTON_BOUNDS["south"] or location.lat > EDMONTON_BOUNDS["north"] or
        location.lng < EDMONTON_BOUNDS["west"] or location.lng > EDMONTON_BOUNDS["east"]):
        return None
        
    row = math.floor((EDMONTON_BOUNDS["north"] - location.lat) / cell_height)
    col = math.floor((location.lng - EDMONTON_BOUNDS["west"]) / cell_width)
    return (row, col)

# --- 4. MAIN ALGORITHM (runAnalysis) ---

def run_analysis(stations: List[Station], incidents: List[Incident]) -> List[GridCell]:
    """Main analysis function to calculate risk scores for grid cells."""
    
    # calc grid size
    rows, cols, lat_dist, lng_dist = calculate_grid_dimensions()
    
    lat_span = EDMONTON_BOUNDS["north"] - EDMONTON_BOUNDS["south"]
    lng_span = EDMONTON_BOUNDS["east"] - EDMONTON_BOUNDS["west"]
    
    cell_height = lat_span / rows
    cell_width = lng_span / cols

    # 1. Generate Grid
    grid = []
    for r in range(rows):
        for c in range(cols):
            north = EDMONTON_BOUNDS["north"] - r * cell_height
            west = EDMONTON_BOUNDS["west"] + c * cell_width
            
            center = Point(north - cell_height / 2, west + cell_width / 2)
            
            if is_point_in_polygon(center, EDMONTON_POLYGON):
                cell = GridCell(
                    id=f"{r}-{c}",
                    row=r,
                    col=c,
                    bounds={
                        "north": north,
                        "south": north - cell_height,
                        "east": west + cell_width,
                        "west": west
                    }
                )
                grid.append(cell)

    grid_map = {cell.id: cell for cell in grid}
    
    # 2. Bin Data to Grid
    for incident in incidents:
        coords = get_cell_from_coords(incident.location, cell_height, cell_width)
        if coords:
            cell_id = f"{coords[0]}-{coords[1]}"
            if cell_id in grid_map:
                grid_map[cell_id].incident_count += 1
                
    for station in stations:
        coords = get_cell_from_coords(station.location, cell_height, cell_width)
        if coords:
            cell_id = f"{coords[0]}-{coords[1]}"
            if cell_id in grid_map:
                grid_map[cell_id].has_station = True

    station_cells = [cell for cell in grid if cell.has_station]
    
    if not station_cells:
        return grid # no statsions, return empty scores

    # 3. Distance Calculation
    max_incident_count = 0
    max_distance = 0
    
    for cell in grid:
        if cell.incident_count > max_incident_count:
            max_incident_count = cell.incident_count
            
        if cell.incident_count > 0 and not cell.has_station:
            min_distance = float('inf')
            
            for s_cell in station_cells:
                dist = calculate_manhattan_distance(cell, s_cell)
                if dist < min_distance:
                    min_distance = dist
            
            cell.distance_to_station = min_distance
            if min_distance > max_distance:
                max_distance = min_distance

    # 4. Scoring
    for cell in grid:
        if cell.incident_count > 0 and not cell.has_station:
            distance_norm = normalize(cell.distance_to_station, 0, max_distance)
            density_norm = normalize(cell.incident_count, 1, max_incident_count)
            
            # Weighted Formula: 40% Distance + 60% Density
            cell.score = (distance_norm * 0.4) + (density_norm * 0.6)
        else:
            cell.score = 0.0

    return grid

# --- TEST CODE ---
if __name__ == "__main__":
    print("=== STARTING BATCH TESTS ===\n")

    # Define diffrent scenerios to test the algo logic
    test_scenarios = [
        {
            "name": "Scenario A: City Center Coverage",
            "desc": "Incidents are near stations. Scores should be LOW.",
            "stations": [
                Station("S1", Point(53.5461, -113.4938)), # Downtown
            ],
            "incidents": [
                Incident("I1", Point(53.5460, -113.4940)), # Very close
                Incident("I2", Point(53.5462, -113.4935)),
                Incident("I3", Point(53.5450, -113.4950))
            ]
        },
        {
            "name": "Scenario B: The 'Gap' Problem",
            "desc": "High incidents far from station. Scores should be HIGH.",
            "stations": [
                Station("S1", Point(53.5000, -113.5000)) # South
            ],
            "incidents": [
                Incident("I1", Point(53.6000, -113.4000)), # North East (Far)
                Incident("I2", Point(53.6000, -113.4000)), # High Density
                Incident("I3", Point(53.6000, -113.4000)),
                Incident("I4", Point(53.6010, -113.4010))
            ]
        },
        {
            "name": "Scenario C: Sparse / Random",
            "desc": "Incidents scatterd randomly. Mixed scores expected.",
            "stations": [
                Station("S1", Point(53.5400, -113.5000)),
                Station("S2", Point(53.4500, -113.4000))
            ],
            "incidents": [
                Incident("I1", Point(53.7000, -113.3000)), # Far outlier
                Incident("I2", Point(53.5410, -113.5010)), # Close to S1
                Incident("I3", Point(53.4550, -113.4050))  # Close to S2
            ]
        }
    ]

    # Loop thru scenerios and run analysis for each
    for scenario in test_scenarios:
        print(f"Running: {scenario['name']}")
        print(f"Goal: {scenario['desc']}")
        
        results = run_analysis(scenario['stations'], scenario['incidents'])
        
        # Filter and sort to find highest risks
        # listing only cells with score > 0
        high_risk_cells = sorted(
            [c for c in results if c.score > 0], 
            key=lambda x: x.score, 
            reverse=True
        )
        
        if not high_risk_cells:
            print(" -> Result: No risk zones detcted (All covered or empty).")
        else:
            print(f" -> Result: Found {len(high_risk_cells)} risk zones.")
            print(" -> Top 3 Critical Zones:")
            for i, cell in enumerate(high_risk_cells[:3]):
                print(f"    {i+1}. {cell}")
        
        print("-" * 40) # seperator line

    print("\n=== ALL TESTS COMPLETED ===")