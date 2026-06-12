import math
from typing import Iterable

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in miles."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def simplify_route(
    coordinates: list[tuple[float, float]],
    interval_miles: float = 2.0,
) -> list[tuple[float, float]]:
    """Reduce dense route geometry for faster fuel-stop calculations."""
    if len(coordinates) <= 2:
        return coordinates

    cumulative = cumulative_route_distances(coordinates)
    simplified = [coordinates[0]]
    last_kept_mile = 0.0

    for index in range(1, len(coordinates) - 1):
        if cumulative[index] - last_kept_mile >= interval_miles:
            simplified.append(coordinates[index])
            last_kept_mile = cumulative[index]

    simplified.append(coordinates[-1])
    return simplified


def cumulative_route_distances(coordinates: list[tuple[float, float]]) -> list[float]:
    """Return cumulative distance in miles for each coordinate along the route."""
    if not coordinates:
        return []

    cumulative = [0.0]
    for index in range(1, len(coordinates)):
        lat1, lng1 = coordinates[index - 1]
        lat2, lng2 = coordinates[index]
        cumulative.append(
            cumulative[-1] + haversine_miles(lat1, lng1, lat2, lng2)
        )
    return cumulative


def sample_route_points(
    coordinates: list[tuple[float, float]],
    interval_miles: float = 15.0,
) -> list[tuple[float, float, float]]:
    """Sample route every `interval_miles`; returns (lat, lng, mile_marker)."""
    if not coordinates:
        return []

    cumulative = cumulative_route_distances(coordinates)
    total_distance = cumulative[-1]
    if total_distance == 0:
        lat, lng = coordinates[0]
        return [(lat, lng, 0.0)]

    samples: list[tuple[float, float, float]] = []
    target_mile = 0.0
    segment_index = 0

    while target_mile <= total_distance:
        while (
            segment_index < len(cumulative) - 1
            and cumulative[segment_index + 1] < target_mile
        ):
            segment_index += 1

        if segment_index >= len(coordinates) - 1:
            lat, lng = coordinates[-1]
            samples.append((lat, lng, total_distance))
            break

        segment_start = cumulative[segment_index]
        segment_end = cumulative[segment_index + 1]
        segment_length = segment_end - segment_start

        if segment_length == 0:
            lat, lng = coordinates[segment_index]
        else:
            ratio = (target_mile - segment_start) / segment_length
            lat1, lng1 = coordinates[segment_index]
            lat2, lng2 = coordinates[segment_index + 1]
            lat = lat1 + (lat2 - lat1) * ratio
            lng = lng1 + (lng2 - lng1) * ratio

        samples.append((lat, lng, target_mile))
        target_mile += interval_miles

    return samples


def project_point_to_route(
    lat: float,
    lng: float,
    coordinates: list[tuple[float, float]],
    cumulative: list[float] | None = None,
) -> tuple[float, float]:
    """Project a point onto the route; returns (mile_marker, distance_from_route_miles)."""
    if not coordinates:
        return 0.0, float("inf")

    if cumulative is None:
        cumulative = cumulative_route_distances(coordinates)

    best_distance = float("inf")
    best_mile = 0.0

    for index in range(len(coordinates) - 1):
        lat1, lng1 = coordinates[index]
        lat2, lng2 = coordinates[index + 1]
        segment_length = cumulative[index + 1] - cumulative[index]

        if segment_length == 0:
            distance = haversine_miles(lat, lng, lat1, lng1)
            mile_marker = cumulative[index]
        else:
            ratio = _closest_point_ratio(lat, lng, lat1, lng1, lat2, lng2)
            ratio = max(0.0, min(1.0, ratio))
            proj_lat = lat1 + (lat2 - lat1) * ratio
            proj_lng = lng1 + (lng2 - lng1) * ratio
            distance = haversine_miles(lat, lng, proj_lat, proj_lng)
            mile_marker = cumulative[index] + segment_length * ratio

        if distance < best_distance:
            best_distance = distance
            best_mile = mile_marker

    return best_mile, best_distance


def _closest_point_ratio(
    lat: float,
    lng: float,
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    x, y = lng, lat
    x1, y1 = lng1, lat1
    x2, y2 = lng2, lat2
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return 0.0
    return ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)


def encode_polyline(coordinates: Iterable[tuple[float, float]]) -> str:
    """Encode (lat, lng) coordinates into a Google polyline string."""
    encoded: list[str] = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in coordinates:
        lat_i = round(lat * 1e5)
        lng_i = round(lng * 1e5)
        encoded.append(_encode_value(lat_i - prev_lat))
        encoded.append(_encode_value(lng_i - prev_lng))
        prev_lat = lat_i
        prev_lng = lng_i

    return "".join(encoded)


def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else (value << 1)
    chunks: list[str] = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)
