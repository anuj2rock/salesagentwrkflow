"""Prompt interpretation strategies for the weather agent."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from typing import List

from ..config import get_settings
from ..schemas import Location, Timeframe, WeatherSpec
from .llm_client import LLMClient, extract_message_content, parse_json_from_content
from .weather_api import GeocodingService


logger = logging.getLogger(__name__)


DEFAULT_METRICS = [
    "temperature_max",
    "temperature_min",
    "precipitation_probability",
]


class RuleBasedPromptInterpreter:
    """Translate a free-form prompt into a structured ``WeatherSpec`` without an LLM."""

    def __init__(self, geocoder: GeocodingService | None = None) -> None:
        self._geocoder = geocoder or GeocodingService()

    async def interpret(self, prompt: str) -> WeatherSpec:
        location_name = self._extract_location(prompt) or "New York City, USA"
        logger.debug("rule-based interpreter extracting location", extra={"location_hint": location_name})
        coordinates = await self._geocoder.geocode(location_name)

        timeframe = self._extract_timeframe(prompt)
        metrics = self._extract_metrics(prompt)
        units = "imperial" if re.search(r"\b(fahrenheit|imperial)\b", prompt, re.I) else "metric"
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


class LLMInterpreter:
    """Use a Hugging Face-hosted LLM to interpret prompts."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        geocoder: GeocodingService | None = None,
        fallback: RuleBasedPromptInterpreter | None = None,
    ) -> None:
        settings = get_settings()
        self._model = settings.llm_model_interpreter
        self._llm_client = llm_client or LLMClient(settings=settings)
        self._geocoder = geocoder or GeocodingService()
        self._fallback = fallback or RuleBasedPromptInterpreter(self._geocoder)

    async def interpret(self, prompt: str) -> WeatherSpec:
        if not self._llm_client.is_configured:
            logger.info("LLM interpreter not configured; using fallback")
            return await self._fallback.interpret(prompt)

        try:
            spec_dict = await self._call_model(prompt)
            location_block = spec_dict.setdefault("location", {})
            if not location_block.get("name"):
                raise ValueError("Location name missing")
            if not location_block.get("latitude") or not location_block.get("longitude"):
                coordinates = await self._geocoder.geocode(location_block["name"])
                location_block["latitude"] = coordinates.latitude
                location_block["longitude"] = coordinates.longitude
            spec = WeatherSpec.model_validate(spec_dict)
        except Exception:  # pragma: no cover - depends on external API
            logger.warning("LLM interpreter failed; falling back", exc_info=True)
            # Fall back to deterministic heuristics if the LLM output is invalid
            return await self._fallback.interpret(prompt)
        return spec

    async def _call_model(self, prompt: str) -> dict:
        schema = {
            "location": {
                "name": "string",
                "latitude": "float",
                "longitude": "float",
            },
            "timeframe": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
            "metrics": ["temperature_max", "temperature_min", "precipitation_probability"],
            "units": "metric|imperial",
            "narrative_tone": "business|casual",
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You convert user weather requests into a JSON object following this schema: "
                    f"{json.dumps(schema)}. Respond with JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        logger.info("calling LLM for prompt interpretation", extra={"model": self._model})
        response = await self._llm_client.chat(messages=messages, model=self._model)
        content = extract_message_content(response)
        logger.debug("LLM interpreter raw content received", extra={"length": len(content)})
        return parse_json_from_content(content)


def build_prompt_interpreter() -> LLMInterpreter | RuleBasedPromptInterpreter:
    """Factory that decides whether to use the LLM or the heuristic interpreter."""

    settings = get_settings()
    llm_client = LLMClient(settings=settings)
    geocoder = GeocodingService()
    fallback = RuleBasedPromptInterpreter(geocoder)
    if llm_client.is_configured:
        return LLMInterpreter(llm_client=llm_client, geocoder=geocoder, fallback=fallback)
    return fallback

