from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from route.serializers import RouteRequestSerializer
from route.services.fuel_optimizer import FuelOptimizationError, FuelOptimizer
from route.services.route_service import RouteService, RouteServiceError
from route.services.station_store import get_station_store


def map_page(request):
    return render(request, "route/map.html")


class RoutePlanView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            route_service = RouteService()
            route = route_service.get_route(
                serializer.validated_data["start"],
                serializer.validated_data["end"],
            )
            fuel_plan = FuelOptimizer(get_station_store()).plan(route.coordinates)
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (RouteServiceError, FuelOptimizationError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        start_input = serializer.validated_data["start"]
        end_input = serializer.validated_data["end"]

        return Response(
            {
                "distance_miles": round(fuel_plan.total_distance_miles, 2),
                "duration_seconds": round(route.duration_seconds),
                "total_fuel_used_gallons": round(fuel_plan.total_fuel_used_gallons, 2),
                "total_cost": round(fuel_plan.total_cost, 2),
                "route_polyline": route.encoded_polyline,
                "start": {
                    "lat": route.start[0],
                    "lng": route.start[1],
                    "label": start_input if isinstance(start_input, str) else "Start",
                },
                "end": {
                    "lat": route.end[0],
                    "lng": route.end[1],
                    "label": end_input if isinstance(end_input, str) else "End",
                },
                "fuel_stops": [
                    {
                        "id": stop.station.id,
                        "name": stop.station.name,
                        "address": stop.station.address,
                        "city": stop.station.city,
                        "state": stop.station.state,
                        "lat": stop.station.lat,
                        "lng": stop.station.lng,
                        "price": round(stop.station.price, 3),
                        "mile_marker": round(stop.mile_marker, 2),
                        "leg_distance_miles": round(stop.leg_distance_miles, 2),
                        "gallons_used": round(stop.gallons_used, 2),
                        "leg_cost": round(stop.leg_cost, 2),
                    }
                    for stop in fuel_plan.fuel_stops
                ],
            }
        )
