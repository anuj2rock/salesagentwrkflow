"""Simple rule-based interpreter that approximates LLM behavior for the POC."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List

from .weather_api import GeocodingService
from ..schemas import Location, Timeframe, WeatherSpec


DEFAULT_METRICS = [
    "temperature_max",
    "temperature_min",
    "precipitation_probability",
]


class PromptInterpreter:
    """Translate a free-form prompt into a structured ``WeatherSpec``."""

    def __init__(self, geocoder: GeocodingService | None = None) -> None:
        self._geocoder = geocoder or GeocodingService()

    async def interpret(self, prompt: str) -> WeatherSpec:
        location_name = self._extract_location(prompt) or "New York City, USA"
        coordinates = await self._geocoder.geocode(location_name)

        timeframe = self._extract_timeframe(prompt)
        metrics = self._extract_metrics(prompt)
        units = "imperial" if re.search(r"\b(fahrenheit|imperial|fahrenheit)\b", prompt, re.I) else "metric"
        tone = "casual" if "casual" in prompt.lower() else "business"

        return WeatherSpec(
            location=Location(name=coordinates.name, latitude=coordinates.latitude, longitude=coordinates.longitude),
            timeframe=timeframe,
            metrics=metrics,
            units=units,
            narrative_tone=tone,
        )

    def _extract_location(self, prompt: str) -> str | None:
        match = re.search(r"in ([A-Za-z\s,]+)", prompt)
        if match:
            return match.group(1).strip()
        return None

    def _extract_timeframe(self, prompt: str) -> Timeframe:
        today = date.today()
        if "next week" in prompt.lower():
            start = today + timedelta(days=1)
            end = start + timedelta(days=6)
        elif "tomorrow" in prompt.lower():
            start = today + timedelta(days=1)
            end = start
        elif match := re.search(r"next (\d{1,2}) days", prompt.lower()):
            days = int(match.group(1))
            start = today
            end = start + timedelta(days=days - 1)
        else:
            start = today
            end = today + timedelta(days=4)
        return Timeframe(start=start, end=end)

    def _extract_metrics(self, prompt: str) -> List[str]:
        metrics = []
        lowered = prompt.lower()
        if "precip" in lowered or "rain" in lowered:
            metrics.append("precipitation_probability")
        if "temperature" in lowered or "temp" in lowered:
            metrics.extend(["temperature_max", "temperature_min"])
        if not metrics:
            metrics.extend(DEFAULT_METRICS)
        return sorted(set(metrics))

