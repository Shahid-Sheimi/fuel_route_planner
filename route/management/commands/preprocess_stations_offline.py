import csv
import json
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Build fuel_stations.json using city/state centroids from US zipcode data "
        "(fast offline fallback; run preprocess_stations for address-level geocoding)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(settings.BASE_DIR / "data/fuel-prices-for-be-assessment.csv"),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--zipcodes",
            default=str(
                settings.BASE_DIR.parent / "location_project" / "core" / "all_us_zipcodes.csv"
            ),
            help="Path to all_us_zipcodes.csv for city/state centroids.",
        )
        parser.add_argument(
            "--output",
            default=str(settings.FUEL_STATIONS_PATH),
            help="Output JSON path for geocoded stations.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv"])
        zipcodes_path = Path(options["zipcodes"])
        output_path = Path(options["output"])

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")
        if not zipcodes_path.exists():
            raise CommandError(
                f"Zipcode file not found: {zipcodes_path}. "
                "Provide --zipcodes or use preprocess_stations with ORS_API_KEY."
            )

        centroids = self._load_city_centroids(zipcodes_path)
        stations = self._load_stations(csv_path, centroids)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(stations, handle, indent=2)

        self.stdout.write(
            self.style.SUCCESS(f"Saved {len(stations)} stations to {output_path}")
        )

    def _load_city_centroids(self, zipcodes_path: Path) -> dict[tuple[str, str], dict]:
        totals: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)

        with zipcodes_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not row["lat"] or not row["lon"]:
                    continue
                city = row["city"].strip().upper()
                state = row["state"].strip().upper()
                totals[(city, state)].append((float(row["lat"]), float(row["lon"])))

        centroids: dict[tuple[str, str], dict] = {}
        for key, points in totals.items():
            lat = sum(point[0] for point in points) / len(points)
            lng = sum(point[1] for point in points) / len(points)
            centroids[key] = {"lat": lat, "lng": lng}

        return centroids

    def _load_stations(
        self,
        csv_path: Path,
        centroids: dict[tuple[str, str], dict],
    ) -> list[dict]:
        stations_by_id: dict[str, dict] = {}
        missing = 0

        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                station_id = row["OPIS Truckstop ID"].strip()
                price = float(row["Retail Price"])
                city = row["City"].strip().upper()
                state = row["State"].strip().upper()
                coords = centroids.get((city, state))
                if coords is None:
                    missing += 1
                    continue

                existing = stations_by_id.get(station_id)
                if existing is None or price < existing["price"]:
                    stations_by_id[station_id] = {
                        "id": station_id,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": row["City"].strip(),
                        "state": row["State"].strip(),
                        "lat": coords["lat"],
                        "lng": coords["lng"],
                        "price": price,
                    }

        if missing:
            self.stderr.write(
                self.style.WARNING(f"Skipped {missing} rows with unknown city/state centroids.")
            )

        return sorted(stations_by_id.values(), key=lambda item: item["id"])
