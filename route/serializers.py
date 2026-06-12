from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.JSONField()
    end = serializers.JSONField()

    def validate_start(self, value):
        return self._validate_location(value, "start")

    def validate_end(self, value):
        return self._validate_location(value, "end")

    def _validate_location(self, value, field_name: str):
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict) and "lat" in value and "lng" in value:
            return {"lat": float(value["lat"]), "lng": float(value["lng"])}
        raise serializers.ValidationError(
            f"{field_name} must be a US address string or {{lat, lng}} coordinates."
        )
