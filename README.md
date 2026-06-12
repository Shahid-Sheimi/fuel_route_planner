# Fuel Route API

A Django REST API and interactive web map that plans driving routes within the USA and recommends **cost-efficient fuel stops** along the way. The app uses real fuel price data from truck stops, assumes a **500-mile vehicle range** and **10 MPG**, and returns total fuel cost, distance, drive time, and an encoded route polyline for map rendering.

---

## Features

- **Route planning** between any two US locations (address or coordinates)
- **Optimal fuel stops** — greedy, constraint-based selection of the cheapest reachable stations
- **Interactive map** — Leaflet.js + OpenStreetMap with route polyline, start/end markers, and numbered fuel stops
- **Trip summary** — distance, drive time, fuel used, total cost, and per-stop breakdown
- **Preprocessed fuel data** — no runtime geocoding of stations (fast responses)
- **Route caching** — repeated start/end pairs are cached for 24 hours
- **Production-ready** — Gunicorn + WhiteNoise static serving + Docker support

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Django 5.2, Django REST Framework |
| Frontend map | Leaflet.js, OpenStreetMap tiles |
| Address geocoding | Nominatim (OpenStreetMap) |
| Route geometry | OpenRouteService (optional) → OSRM fallback |
| Static files (prod) | WhiteNoise + `collectstatic` |
| Server (prod) | Gunicorn |

---

## Project Structure

```
FuelRouteApi/
├── FuelRouteApi/          # Django project settings & URLs
├── route/
│   ├── services/
│   │   ├── geo.py              # Haversine, polyline, route sampling
│   │   ├── route_service.py    # Geocoding + routing (ORS/OSRM)
│   │   ├── station_store.py    # In-memory fuel station index
│   │   └── fuel_optimizer.py   # Fuel stop selection logic
│   ├── management/commands/
│   │   ├── preprocess_stations.py          # ORS geocoding (accurate)
│   │   └── preprocess_stations_offline.py  # Zipcode centroids (fast)
│   ├── templates/route/map.html
│   ├── static/route/           # CSS & JS for the map UI
│   ├── views.py
│   ├── serializers.py
│   └── urls.py
├── data/
│   └── fuel_stations.json      # Preprocessed station data (generated)
├── fuel-prices-for-be-assessment.csv
├── Dockerfile
├── requirements.txt
└── manage.py
```

---

## Prerequisites

- Python 3.12+
- `pip` and optionally `venv`
- Fuel station data (`data/fuel_stations.json`) — see [Data Setup](#data-setup)
- Optional: [OpenRouteService](https://openrouteservice.org) API key (routing falls back to OSRM if unavailable)

---

## Quick Start (Development)

### 1. Clone and set up the environment

```bash
git clone https://github.com/Shahid-Sheimi/fuel_route_planner.git
cd fuel_route_planner
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
ORS_API_KEY=your_openrouteservice_api_key_here
```

> **Note:** The ORS key is optional. If missing or disallowed, routing automatically uses the free OSRM public API.

### 3. Prepare fuel station data

If `data/fuel_stations.json` does not exist yet, run the offline preprocessor (fast, no API key):

```bash
python manage.py preprocess_stations_offline
```

For more accurate highway-level coordinates (slower, requires ORS key):

```bash
python manage.py preprocess_stations
```

This command is resumable — progress is saved in `data/geocode_cache.json`.

### 4. Run the development server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

---

## Production (Gunicorn)

Gunicorn does **not** serve static files on its own. This project uses **WhiteNoise** to handle CSS/JS.

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
gunicorn FuelRouteApi.wsgi:application --bind 0.0.0.0:8000
```

With `DEBUG=True`, WhiteNoise can serve static files directly from app folders without running `collectstatic`.

---

## Docker

### Build

```bash
docker build -t fuel-route-api .
```

The image automatically runs `collectstatic` during build and starts Gunicorn on port 8000.

### Run

```bash
docker run -p 8000:8000 --env-file .env fuel-route-api
```

Or pass environment variables manually:

```bash
docker run -p 8000:8000 \
  -e ORS_API_KEY=your_key \
  -e ALLOWED_HOSTS=localhost,127.0.0.1 \
  fuel-route-api
```

Open **http://localhost:8000/**

> Ensure `data/fuel_stations.json` exists in the project before building the image (it is copied into the container at build time).

---

## API Reference

### `POST /api/route/`

Plan a route and compute optimal fuel stops.

**Request body**

```json
{
  "start": "New York, NY",
  "end": "Chicago, IL"
}
```

Locations can be a **US address string** or **coordinates**:

```json
{
  "start": { "lat": 40.7128, "lng": -74.0060 },
  "end": { "lat": 41.8781, "lng": -87.6298 }
}
```

Coordinate strings are also accepted: `"40.7128, -74.0060"`

**Success response** `200 OK`

```json
{
  "distance_miles": 793.2,
  "duration_seconds": 43200,
  "total_fuel_used_gallons": 79.32,
  "total_cost": 242.63,
  "route_polyline": "encoded_polyline_string",
  "start": {
    "lat": 40.7128,
    "lng": -74.006,
    "label": "New York, NY"
  },
  "end": {
    "lat": 41.8781,
    "lng": -87.6298,
    "label": "Chicago, IL"
  },
  "fuel_stops": [
    {
      "id": "639",
      "name": "SHEETZ #639",
      "address": "I-80, EXIT 123",
      "city": "Somewhere",
      "state": "PA",
      "lat": 41.0,
      "lng": -78.5,
      "price": 3.059,
      "mile_marker": 380.5,
      "leg_distance_miles": 380.5,
      "gallons_used": 38.05,
      "leg_cost": 116.39
    }
  ]
}
```

**Error responses**

| Status | Meaning |
|--------|---------|
| `400` | Invalid input, geocoding failure, routing failure, or no reachable fuel stops |
| `503` | Fuel station data file not found — run preprocessing first |

**Example with curl**

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "New York, NY", "end": "Chicago, IL"}'
```

---

## Web UI

| URL | Description |
|-----|-------------|
| `GET /` | Interactive Fuel Route Planner map |
| `POST /api/route/` | JSON API endpoint |

The map UI includes:

- Full-viewport layout (sidebar scrolls independently; map always visible)
- Route toolbar with distance, drive time, fuel, cost, and stop count
- Green **A** (start) and red **B** (end) markers
- Numbered orange fuel stop markers
- Mile scale control and OpenStreetMap attribution

---

## Data Setup

### Source CSV

Fuel prices come from `fuel-prices-for-be-assessment.csv` with columns:

| Column | Description |
|--------|-------------|
| OPIS Truckstop ID | Unique station identifier |
| Truckstop Name | Station name |
| Address | Street / highway address |
| City | City |
| State | US state code |
| Rack ID | Pricing rack reference |
| Retail Price | Price per gallon (USD) |

### Preprocessing commands

| Command | Description | API key required |
|---------|-------------|------------------|
| `preprocess_stations_offline` | Geocodes stations using city/state centroids from US zipcode data | No |
| `preprocess_stations` | Geocodes stations via OpenRouteService (address-level accuracy) | Yes |

```bash
# Fast offline (recommended for first run)
python manage.py preprocess_stations_offline

# Accurate ORS geocoding (resumable)
python manage.py preprocess_stations

# Limit for testing
python manage.py preprocess_stations --limit 100
```

Output is written to `data/fuel_stations.json`.

---

## How It Works

```
Start / End input
       │
       ▼
  Nominatim geocoding (addresses → lat/lng)
       │
       ▼
  Route geometry (ORS → OSRM fallback)
       │
       ▼
  Sample route every 15 miles
       │
       ▼
  Find nearby stations (Haversine, 40 mi radius)
       │
       ▼
  Greedy fuel optimizer
  (500 mi range, cheapest reachable station)
       │
       ▼
  JSON response + Leaflet map render
```

### Fuel optimization rules

- Vehicle range: **500 miles** per full tank
- Fuel economy: **10 MPG**
- Stations must be within **50 miles** of the route corridor
- At each step, pick the **cheapest** station that is reachable and still allows completing the trip
- Total fuel cost = sum of (gallons per leg × station price for that leg)

### Performance

- Fuel stations loaded **in memory** at startup (spatial grid index)
- Route results **cached** for 24 hours
- Dense OSRM geometry is **simplified** before fuel calculations
- No runtime geocoding of fuel stations

---

## Configuration

Settings in `FuelRouteApi/settings.py` (or via environment):

| Setting | Default | Description |
|---------|---------|-------------|
| `ORS_API_KEY` | — | OpenRouteService API key (optional) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `VEHICLE_RANGE_MILES` | `500` | Max miles per tank |
| `VEHICLE_MPG` | `10` | Miles per gallon |
| `FUEL_SEARCH_RADIUS_MILES` | `40` | Station search radius per sample point |
| `ROUTE_SAMPLE_INTERVAL_MILES` | `15` | Distance between route sample points |
| `ROUTE_CORRIDOR_MILES` | `50` | Max distance a station can be from the route |
| `ROUTE_CACHE_TIMEOUT` | `86400` | Route cache TTL in seconds |

---

## Running Tests

```bash
python manage.py test route
```

---

## Troubleshooting

### Static files 404 with Gunicorn

```bash
pip install whitenoise
python manage.py collectstatic --noinput
```

Restart Gunicorn after installing dependencies.

### `Fuel station data not found`

```bash
python manage.py preprocess_stations_offline
```

### `Routing failed (403)` from OpenRouteService

Your ORS key may not include the Directions API. The app automatically falls back to OSRM — no action needed unless you specifically require ORS.

### Map not loading CSS/JS after code changes

Hard-refresh the browser (`Ctrl+Shift+R`) or restart the server.

### Docker container starts but map is blank

Confirm `data/fuel_stations.json` was present when the image was built:

```bash
docker run --rm fuel-route-api ls -la /app/data/
```

---

## License

Assessment / educational project. Fuel price data provided via `fuel-prices-for-be-assessment.csv`.
