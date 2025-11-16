"""Open-Meteo implementation of the provider client interface."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, List, Mapping

import httpx

from ...schemas import ProviderDataset, ReportSpec, WeatherDataPoint
from .base import BaseProviderClient, ProviderRequestError, SignedRequest

logger = logging.getLogger(__name__)

DEFAULT_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoProvider(BaseProviderClient):
    """Provider backed by Open-Meteo's daily forecast endpoint."""

    METRIC_MAP = {
        "temperature_max": "temperature_2m_max",
        "temperature_min": "temperature_2m_min",
        "precipitation_probability": "precipitation_probability_mean",
    }

    def build_payload(self, spec: ReportSpec) -> Mapping[str, str | float]:
        daily_params = [self.METRIC_MAP[m] for m in spec.metrics if m in self.METRIC_MAP]
        if not daily_params:
            raise ProviderRequestError("No supported metrics requested for Open-Meteo")
        params: dict[str, str | float] = {
            "latitude": spec.location.latitude,
            "longitude": spec.location.longitude,
            "daily": ",".join(daily_params),
            "timezone": "auto",
            "start_date": spec.timeframe.start.isoformat(),
            "end_date": spec.timeframe.end.isoformat(),
        }
        if spec.units == "imperial":
            params["temperature_unit"] = "fahrenheit"
        return params

    def sign_request(self, payload: Mapping[str, str | float]) -> SignedRequest:
        # Open-Meteo does not require authentication.
        return SignedRequest(payload=payload)

    async def dispatch(self, request: SignedRequest, spec: ReportSpec) -> Mapping[str, Any]:  # type: ignore[override]
        url = self.config.get("weather_url", DEFAULT_WEATHER_URL)
        timeout = self.config.get("timeout", 15)
        logger.info(
            "fetching weather data",
            extra={
                "provider_id": self.provider_id,
                "location": spec.location.name,
                "start": spec.timeframe.start.isoformat(),
                "end": spec.timeframe.end.isoformat(),
            },
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=dict(request.payload))
            response.raise_for_status()
        return response.json()

    def parse_response(self, payload: Mapping[str, Any], spec: ReportSpec) -> ProviderDataset:  # type: ignore[override]
        daily = payload.get("daily", {}) if isinstance(payload, Mapping) else {}
        dates = [date.fromisoformat(day) for day in daily.get("time", [])]
        data_points: List[WeatherDataPoint] = []
        for idx, current_date in enumerate(dates):
            record = WeatherDataPoint(date=current_date)
            if "temperature_max" in spec.metrics:
                temps = daily.get("temperature_2m_max", [])
                record.temperature_max = temps[idx] if idx < len(temps) else None
            if "temperature_min" in spec.metrics:
                temps_min = daily.get("temperature_2m_min", [])
                record.temperature_min = temps_min[idx] if idx < len(temps_min) else None
            if "precipitation_probability" in spec.metrics:
                precip = daily.get("precipitation_probability_mean", [])
                record.precipitation_probability = precip[idx] if idx < len(precip) else None
            data_points.append(record)
        logger.info(
            "weather data parsed",
            extra={"provider_id": self.provider_id, "location": spec.location.name, "days": len(data_points)},
        )
        return ProviderDataset(provider_id=self.provider_id, source="open-meteo", data=data_points)
