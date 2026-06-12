import hashlib
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from route.services.geo import encode_polyline


class RouteServiceError(Exception):
    pass


@dataclass
class RouteResult:
    coordinates: list[tuple[float, float]]
    distance_miles: float
    duration_seconds: float
    encoded_polyline: str
    start: tuple[float, float]
    end: tuple[float, float]


class RouteService:
    ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
    OSRM_DIRECTIONS_URL = "https://router.project-osrm.org/route/v1/driving"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self) -> None:
        self.api_key = settings.ORS_API_KEY
        self.placeholder_key = "your_openrouteservice_api_key_here"

    def resolve_location(self, location: str | dict) -> tuple[float, float]:
        if isinstance(location, dict):
            return float(location["lat"]), float(location["lng"])

        location = location.strip()
        coord_match = re.match(
            r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$",
            location,
        )
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            return lat, lng

        return self._geocode(location)

    def get_route(
        self,
        start: str | dict,
        end: str | dict,
    ) -> RouteResult:
        start_coords = self.resolve_location(start)
        end_coords = self.resolve_location(end)
        cache_key = self._cache_key(start_coords, end_coords)
        cached = cache.get(cache_key)
        if cached:
            return RouteResult(**cached)

        route = self._fetch_route(start_coords, end_coords)
        cache.set(cache_key, route.__dict__, settings.ROUTE_CACHE_TIMEOUT)
        return route

    def _cache_key(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> str:
        payload = f"{start[0]:.4f},{start[1]:.4f}|{end[0]:.4f},{end[1]:.4f}"
        return "route:" + hashlib.sha256(payload.encode()).hexdigest()

    def _geocode(self, query: str) -> tuple[float, float]:
        try:
            response = requests.get(
                self.NOMINATIM_URL,
                params={
                    "q": f"{query}, USA",
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "us",
                },
                headers={"User-Agent": "FuelRouteApi/1.0"},
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RouteServiceError(f"Geocoding failed for '{query}': {exc}") from exc

        results = response.json()
        if not results:
            raise RouteServiceError(f"Could not geocode location: {query}")

        return float(results[0]["lat"]), float(results[0]["lon"])

    def _fetch_route(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> RouteResult:
        if self._ors_available():
            try:
                return self._fetch_route_ors(start, end)
            except RouteServiceError:
                pass

        return self._fetch_route_osrm(start, end)

    def _ors_available(self) -> bool:
        return bool(self.api_key and self.api_key != self.placeholder_key)

    def _fetch_route_ors(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> RouteResult:
        response = requests.post(
            self.ORS_DIRECTIONS_URL,
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "coordinates": [
                    [start[1], start[0]],
                    [end[1], end[0]],
                ]
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise RouteServiceError(
                f"OpenRouteService routing failed ({response.status_code}): "
                f"{response.text[:200]}"
            )

        payload = response.json()
        features = payload.get("features", [])
        if not features:
            raise RouteServiceError("No route found between start and end locations.")

        geometry = features[0]["geometry"]["coordinates"]
        coordinates = [(lat, lng) for lng, lat in geometry]
        summary = features[0]["properties"]["summary"]
        distance_meters = summary["distance"]
        duration_seconds = summary.get("duration", 0)

        return self._build_route_result(
            start, end, coordinates, distance_meters, duration_seconds
        )

    def _fetch_route_osrm(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> RouteResult:
        coordinates_path = f"{start[1]},{start[0]};{end[1]},{end[0]}"
        try:
            response = requests.get(
                f"{self.OSRM_DIRECTIONS_URL}/{coordinates_path}",
                params={"overview": "full", "geometries": "geojson"},
                headers={"User-Agent": "FuelRouteApi/1.0"},
                timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RouteServiceError(f"Routing failed: {exc}") from exc

        payload = response.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            message = payload.get("message", "No route found between start and end locations.")
            raise RouteServiceError(f"Routing failed: {message}")

        route = payload["routes"][0]
        geometry = route["geometry"]["coordinates"]
        coordinates = [(lat, lng) for lng, lat in geometry]
        distance_meters = route["distance"]
        duration_seconds = route.get("duration", 0)

        return self._build_route_result(
            start, end, coordinates, distance_meters, duration_seconds
        )

    def _build_route_result(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        coordinates: list[tuple[float, float]],
        distance_meters: float,
        duration_seconds: float,
    ) -> RouteResult:
        distance_miles = distance_meters * 0.000621371
        if not duration_seconds:
            duration_seconds = (distance_miles / 55) * 3600

        return RouteResult(
            coordinates=coordinates,
            distance_miles=distance_miles,
            duration_seconds=duration_seconds,
            encoded_polyline=encode_polyline(coordinates),
            start=start,
            end=end,
        )
