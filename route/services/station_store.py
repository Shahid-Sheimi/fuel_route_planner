import json
import math
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from route.services.geo import haversine_miles


@dataclass(frozen=True)
class FuelStation:
    id: str
    name: str
    address: str
    city: str
    state: str
    lat: float
    lng: float
    price: float


class StationStore:
    """In-memory fuel station index loaded from preprocessed JSON."""

    def __init__(self, stations: list[FuelStation]):
        self.stations = stations
        self._grid: dict[tuple[int, int], list[FuelStation]] = {}
        self._build_grid()

    @classmethod
    def load(cls) -> "StationStore":
        path = Path(settings.FUEL_STATIONS_PATH)
        if not path.exists():
            raise FileNotFoundError(
                f"Fuel station data not found at {path}. "
                "Run: python manage.py preprocess_stations"
            )

        with path.open(encoding="utf-8") as handle:
            raw_stations = json.load(handle)

        stations = [
            FuelStation(
                id=str(item["id"]),
                name=item["name"],
                address=item.get("address", ""),
                city=item.get("city", ""),
                state=item.get("state", ""),
                lat=float(item["lat"]),
                lng=float(item["lng"]),
                price=float(item["price"]),
            )
            for item in raw_stations
        ]
        return cls(stations)

    def _build_grid(self, cell_size: float = 1.0) -> None:
        for station in self.stations:
            cell = (
                int(math.floor(station.lat / cell_size)),
                int(math.floor(station.lng / cell_size)),
            )
            self._grid.setdefault(cell, []).append(station)

    def nearby(
        self,
        lat: float,
        lng: float,
        radius_miles: float,
    ) -> list[FuelStation]:
        cell_size = 1.0
        lat_cell = int(math.floor(lat / cell_size))
        lng_cell = int(math.floor(lng / cell_size))
        cell_radius = int(math.ceil(radius_miles / 69)) + 1

        candidates: list[FuelStation] = []
        seen: set[str] = set()
        for d_lat in range(-cell_radius, cell_radius + 1):
            for d_lng in range(-cell_radius, cell_radius + 1):
                for station in self._grid.get((lat_cell + d_lat, lng_cell + d_lng), []):
                    if station.id in seen:
                        continue
                    seen.add(station.id)
                    if haversine_miles(lat, lng, station.lat, station.lng) <= radius_miles:
                        candidates.append(station)

        return candidates


_store: StationStore | None = None


def get_station_store() -> StationStore:
    global _store
    if _store is None:
        _store = StationStore.load()
    return _store
