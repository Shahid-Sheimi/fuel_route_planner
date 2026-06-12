import csv
import json
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Geocode fuel stations from CSV and save preprocessed JSON for runtime use."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(settings.BASE_DIR / "data/fuel-prices-for-be-assessment.csv"),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--output",
            default=str(settings.FUEL_STATIONS_PATH),
            help="Output JSON path for geocoded stations.",
        )
        parser.add_argument(
            "--cache",
            default=str(settings.GEOCODE_CACHE_PATH),
            help="Geocode cache path for resumable preprocessing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process only the first N unique stations (0 = all).",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.2,
            help="Delay between geocode requests in seconds.",
        )

    def handle(self, *args, **options):
        api_key = settings.ORS_API_KEY
        if not api_key:
            raise CommandError("ORS_API_KEY is not configured in .env")

        csv_path = Path(options["csv"])
        output_path = Path(options["output"])
        cache_path = Path(options["cache"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        stations = self._load_csv(csv_path)
        if options["limit"]:
            stations = stations[: options["limit"]]

        cache = self._load_cache(cache_path)
        geocoded: list[dict] = []
        failures = 0

        self.stdout.write(f"Processing {len(stations)} unique stations...")

        for index, station in enumerate(stations, start=1):
            cache_key = station["id"]
            coords = cache.get(cache_key)

            if coords is None:
                coords = self._geocode_station(station, api_key)
                if coords:
                    cache[cache_key] = coords
                    if index % 25 == 0:
                        self._save_cache(cache_path, cache)
                else:
                    failures += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Failed to geocode station {station['id']}: {station['name']}"
                        )
                    )
                    time.sleep(options["delay"])
                    continue

                time.sleep(options["delay"])

            geocoded.append(
                {
                    "id": station["id"],
                    "name": station["name"],
                    "address": station["address"],
                    "city": station["city"],
                    "state": station["state"],
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                    "price": station["price"],
                }
            )

            if index % 100 == 0:
                self.stdout.write(f"Geocoded {index}/{len(stations)} stations...")
                self._save_cache(cache_path, cache)

        self._save_cache(cache_path, cache)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(geocoded, handle, indent=2)

        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {len(geocoded)} stations to {output_path} ({failures} failures)."
            )
        )

    def _load_csv(self, csv_path: Path) -> list[dict]:
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        stations_by_id: dict[str, dict] = {}
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                station_id = row["OPIS Truckstop ID"].strip()
                price = float(row["Retail Price"])
                existing = stations_by_id.get(station_id)
                if existing is None or price < existing["price"]:
                    stations_by_id[station_id] = {
                        "id": station_id,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": row["City"].strip(),
                        "state": row["State"].strip(),
                        "price": price,
                    }

        return sorted(stations_by_id.values(), key=lambda item: item["id"])

    def _load_cache(self, cache_path: Path) -> dict:
        if not cache_path.exists():
            return {}
        with cache_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _save_cache(self, cache_path: Path, cache: dict) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle)

    def _geocode_station(self, station: dict, api_key: str) -> dict | None:
        queries = [
            f"{station['address']}, {station['city']}, {station['state']}, USA",
            f"{station['city']}, {station['state']}, USA",
        ]

        for query in queries:
            response = requests.get(
                "https://api.openrouteservice.org/geocode/search",
                params={
                    "api_key": api_key,
                    "text": query,
                    "boundary.country": "US",
                    "size": 1,
                },
                timeout=30,
            )
            if response.status_code >= 400:
                continue

            features = response.json().get("features", [])
            if not features:
                continue

            lng, lat = features[0]["geometry"]["coordinates"]
            return {"lat": lat, "lng": lng}

        return None
