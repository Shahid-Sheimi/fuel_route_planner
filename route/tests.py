from django.test import SimpleTestCase, override_settings

from route.services.fuel_optimizer import FuelOptimizer
from route.services.geo import (
    cumulative_route_distances,
    encode_polyline,
    haversine_miles,
    sample_route_points,
)
from route.services.station_store import FuelStation, StationStore


class GeoTests(SimpleTestCase):
    def test_haversine_known_distance(self):
        # New York to Philadelphia is roughly 80 miles.
        distance = haversine_miles(40.7128, -74.0060, 39.9526, -75.1652)
        self.assertGreater(distance, 70)
        self.assertLess(distance, 95)

    def test_sample_route_points(self):
        coordinates = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        samples = sample_route_points(coordinates, interval_miles=30)
        self.assertGreaterEqual(len(samples), 2)
        self.assertEqual(samples[0][2], 0.0)

    def test_encode_polyline_roundtrip_shape(self):
        coordinates = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        encoded = encode_polyline(coordinates)
        self.assertIsInstance(encoded, str)
        self.assertGreater(len(encoded), 10)


class FuelOptimizerTests(SimpleTestCase):
    def test_short_route_needs_no_fuel_stops(self):
        store = StationStore(
            [
                FuelStation(
                    id="1",
                    name="Test Stop",
                    address="",
                    city="",
                    state="",
                    lat=40.0,
                    lng=-100.0,
                    price=3.0,
                )
            ]
        )
        coordinates = [(40.0, -100.0), (40.5, -100.0)]
        plan = FuelOptimizer(store).plan(coordinates)
        self.assertEqual(plan.fuel_stops, [])
        self.assertGreater(plan.total_distance_miles, 0)

    @override_settings(
        VEHICLE_RANGE_MILES=120,
        FUEL_SEARCH_RADIUS_MILES=80,
        ROUTE_CORRIDOR_MILES=80,
    )
    def test_long_route_selects_cheapest_reachable_station(self):
        store = StationStore(
            [
                FuelStation(
                    id="1",
                    name="Expensive",
                    address="",
                    city="",
                    state="",
                    lat=40.0,
                    lng=-99.2,
                    price=5.0,
                ),
                FuelStation(
                    id="2",
                    name="Cheap",
                    address="",
                    city="",
                    state="",
                    lat=40.0,
                    lng=-98.8,
                    price=2.5,
                ),
                FuelStation(
                    id="3",
                    name="Backup",
                    address="",
                    city="",
                    state="",
                    lat=40.8,
                    lng=-97.5,
                    price=3.0,
                ),
            ]
        )
        coordinates = [(40.0, -100.0), (40.0, -99.0), (41.0, -98.0), (41.5, -97.0)]
        cumulative = cumulative_route_distances(coordinates)
        self.assertGreater(cumulative[-1], 120)

        plan = FuelOptimizer(store).plan(coordinates)
        self.assertGreaterEqual(len(plan.fuel_stops), 1)
        self.assertEqual(plan.fuel_stops[0].station.id, "2")
