from dataclasses import dataclass

from django.conf import settings

from route.services.geo import (
    cumulative_route_distances,
    project_point_to_route,
    sample_route_points,
    simplify_route,
)
from route.services.station_store import FuelStation, StationStore


class FuelOptimizationError(Exception):
    pass


@dataclass
class FuelStop:
    station: FuelStation
    mile_marker: float
    leg_distance_miles: float
    gallons_used: float
    leg_cost: float


@dataclass
class FuelPlan:
    fuel_stops: list[FuelStop]
    total_distance_miles: float
    total_fuel_used_gallons: float
    total_cost: float


class FuelOptimizer:
    def __init__(self, station_store: StationStore) -> None:
        self.station_store = station_store
        self.range_miles = settings.VEHICLE_RANGE_MILES
        self.mpg = settings.VEHICLE_MPG
        self.search_radius_miles = settings.FUEL_SEARCH_RADIUS_MILES
        self.sample_interval_miles = settings.ROUTE_SAMPLE_INTERVAL_MILES
        self.max_corridor_miles = settings.ROUTE_CORRIDOR_MILES

    def plan(self, coordinates: list[tuple[float, float]]) -> FuelPlan:
        if len(coordinates) < 2:
            raise FuelOptimizationError("Route must contain at least two points.")

        cumulative = cumulative_route_distances(coordinates)
        total_distance = cumulative[-1]
        if total_distance == 0:
            raise FuelOptimizationError("Route distance is zero.")

        simplified = simplify_route(coordinates, interval_miles=2.0)
        simplified_cumulative = cumulative_route_distances(simplified)
        route_stations = self._stations_along_route(simplified, simplified_cumulative)
        selected = self._select_stations(route_stations, total_distance)
        fuel_stops, total_cost = self._build_fuel_stops(selected, total_distance)

        return FuelPlan(
            fuel_stops=fuel_stops,
            total_distance_miles=total_distance,
            total_fuel_used_gallons=total_distance / self.mpg,
            total_cost=total_cost,
        )

    def _stations_along_route(
        self,
        coordinates: list[tuple[float, float]],
        cumulative: list[float],
    ) -> list[dict]:
        sample_points = sample_route_points(
            coordinates,
            interval_miles=self.sample_interval_miles,
        )
        candidates: dict[str, dict] = {}

        for lat, lng, _sample_mile in sample_points:
            for station in self.station_store.nearby(
                lat,
                lng,
                radius_miles=self.search_radius_miles,
            ):
                mile_marker, distance_from_route = project_point_to_route(
                    station.lat,
                    station.lng,
                    coordinates,
                    cumulative,
                )
                if distance_from_route > self.max_corridor_miles:
                    continue

                existing = candidates.get(station.id)
                if existing is None or station.price < existing["station"].price:
                    candidates[station.id] = {
                        "station": station,
                        "mile_marker": mile_marker,
                    }

        return sorted(candidates.values(), key=lambda item: item["mile_marker"])

    def _select_stations(
        self,
        route_stations: list[dict],
        total_distance: float,
    ) -> list[dict]:
        if total_distance <= self.range_miles:
            return []

        current_mile = 0.0
        selected: list[dict] = []

        while current_mile + self.range_miles < total_distance:
            reachable = [
                item
                for item in route_stations
                if current_mile < item["mile_marker"] <= current_mile + self.range_miles
            ]
            if not reachable:
                raise FuelOptimizationError(
                    f"No fuel stations reachable within {self.range_miles:.0f} miles "
                    f"after mile {current_mile:.1f}."
                )

            valid = [
                item
                for item in reachable
                if self._can_continue_from(item["mile_marker"], route_stations, total_distance)
            ]
            if not valid:
                valid = reachable

            chosen = min(
                valid,
                key=lambda item: (item["station"].price, -item["mile_marker"]),
            )
            selected.append(chosen)
            current_mile = chosen["mile_marker"]

        return selected

    def _can_continue_from(
        self,
        mile_marker: float,
        route_stations: list[dict],
        total_distance: float,
    ) -> bool:
        if mile_marker + self.range_miles >= total_distance:
            return True

        return any(
            station["mile_marker"] > mile_marker
            and station["mile_marker"] <= mile_marker + self.range_miles
            for station in route_stations
        )

    def _build_fuel_stops(
        self,
        selected: list[dict],
        total_distance: float,
    ) -> tuple[list[FuelStop], float]:
        if not selected:
            return [], 0.0

        fuel_stops: list[FuelStop] = []
        total_cost = 0.0
        leg_starts = [0.0] + [item["mile_marker"] for item in selected]
        leg_ends = [item["mile_marker"] for item in selected] + [total_distance]

        for index, item in enumerate(selected):
            leg_distance = leg_ends[index] - leg_starts[index]
            gallons_used = leg_distance / self.mpg
            leg_cost = gallons_used * item["station"].price
            total_cost += leg_cost
            fuel_stops.append(
                FuelStop(
                    station=item["station"],
                    mile_marker=item["mile_marker"],
                    leg_distance_miles=leg_distance,
                    gallons_used=gallons_used,
                    leg_cost=leg_cost,
                )
            )

        final_leg = total_distance - selected[-1]["mile_marker"]
        if final_leg > 0:
            gallons_used = final_leg / self.mpg
            total_cost += gallons_used * selected[-1]["station"].price

        return fuel_stops, total_cost
