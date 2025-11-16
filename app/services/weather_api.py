"""HTTP clients for geocoding and weather data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List

import httpx

from ..schemas import Location, WeatherDataPoint, WeatherDataset

GEOCODER_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class GeocodeResult:
    name: str
    latitude: float
    longitude: float


class GeocodingService:
    """Thin wrapper around Open-Meteo's geocoding endpoint."""

    async def geocode(self, location: str) -> GeocodeResult:
        params = {"name": location, "count": 1}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(GEOCODER_URL, params=params)
            response.raise_for_status()
        payload = response.json()
        first = payload.get("results", [{}])[0]
        if not first:
            raise ValueError(f"Could not geocode location: {location}")
        return GeocodeResult(name=first.get("name", location), latitude=first["latitude"], longitude=first["longitude"])


class WeatherAPIClient:
    """Client for Open-Meteo forecast API."""

    METRIC_MAP = {
        "temperature_max": "temperature_2m_max",
        "temperature_min": "temperature_2m_min",
        "precipitation_probability": "precipitation_probability_mean",
    }

    async def fetch_daily_metrics(
        self,
        *,
        location: Location,
        timeframe_start: date,
        timeframe_end: date,
        metrics: Iterable[str],
        units: str = "metric",
    ) -> WeatherDataset:
        daily_params = [self.METRIC_MAP[m] for m in metrics if m in self.METRIC_MAP]
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": ",".join(daily_params),
            "timezone": "auto",
            "start_date": timeframe_start.isoformat(),
            "end_date": timeframe_end.isoformat(),
        }
        if units == "imperial":
            params["temperature_unit"] = "fahrenheit"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(WEATHER_URL, params=params)
            response.raise_for_status()
        return self._parse_dataset(response.json(), metrics)

    def _parse_dataset(self, payload: dict, metrics: Iterable[str]) -> WeatherDataset:
        daily = payload.get("daily", {})
        dates = [date.fromisoformat(day) for day in daily.get("time", [])]
        data_points: List[WeatherDataPoint] = []
        for idx, current_date in enumerate(dates):
            record = WeatherDataPoint(date=current_date)
            if "temperature_max" in metrics:
                temps = daily.get("temperature_2m_max", [])
                record.temperature_max = temps[idx] if idx < len(temps) else None
            if "temperature_min" in metrics:
                temps_min = daily.get("temperature_2m_min", [])
                record.temperature_min = temps_min[idx] if idx < len(temps_min) else None
            if "precipitation_probability" in metrics:
                precip = daily.get("precipitation_probability_mean", [])
                record.precipitation_probability = precip[idx] if idx < len(precip) else None
            data_points.append(record)
        return WeatherDataset(source="open-meteo", data=data_points)

