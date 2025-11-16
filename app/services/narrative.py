"""Narrative generation helpers backed by an optional LLM."""
from __future__ import annotations

import logging
from statistics import mean
from typing import Any, Dict

from ..config import get_settings
from ..schemas import Narrative, WeatherDataset
from .llm_client import LLMClient, extract_message_content


logger = logging.getLogger(__name__)


def _fallback_summary(dataset: WeatherDataset) -> Narrative:
    if not dataset.data:
        return Narrative(title="Weather Summary", summary="No data available for the requested period.")

    temps_max = [point.temperature_max for point in dataset.data if point.temperature_max is not None]
    temps_min = [point.temperature_min for point in dataset.data if point.temperature_min is not None]
    precip = [point.precipitation_probability for point in dataset.data if point.precipitation_probability is not None]

    lines = []
    if temps_max:
        lines.append(f"Average daytime high: {mean(temps_max):.1f}°")
    if temps_min:
        lines.append(f"Average nighttime low: {mean(temps_min):.1f}°")
    if precip:
        lines.append(f"Mean precipitation probability: {mean(precip):.0f}%")

    summary = ". ".join(lines) + "."
    return Narrative(title="Weather outlook", summary=summary)


class NarrativeService:
    """Generate a richer narrative by prompting the configured LLM."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        settings = get_settings()
        self._model = settings.llm_model_narrative
        self._llm_client = llm_client or LLMClient(settings=settings)

    async def generate(self, dataset: WeatherDataset, tone: str = "business") -> Narrative:
        if not self._llm_client.is_configured:
            logger.info("LLM narrative disabled; using fallback summary")
            return _fallback_summary(dataset)

        stats = self._summarize_dataset(dataset)
        if not stats:
            logger.warning("Narrative skipped due to empty dataset")
            return _fallback_summary(dataset)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful weather analyst. Use the provided structured data to write a "
                    f"short {tone} summary. Keep it under 120 words."
                ),
            },
            {
                "role": "user",
                "content": f"Data: {stats}",
            },
        ]

        try:
            logger.info("calling LLM for narrative", extra={"model": self._model})
            response = await self._llm_client.chat(messages=messages, model=self._model)
            content = extract_message_content(response).strip()
            if not content:
                raise ValueError("Empty LLM narrative")
            logger.debug("narrative generated", extra={"length": len(content)})
            return Narrative(title="Weather outlook", summary=content)
        except Exception:  # pragma: no cover - depends on external API
            logger.warning("LLM narrative failed; returning fallback", exc_info=True)
            return _fallback_summary(dataset)

    def _summarize_dataset(self, dataset: WeatherDataset) -> Dict[str, Any]:
        if not dataset.data:
            return {}
        temps_max = [point.temperature_max for point in dataset.data if point.temperature_max is not None]
        temps_min = [point.temperature_min for point in dataset.data if point.temperature_min is not None]
        precip = [point.precipitation_probability for point in dataset.data if point.precipitation_probability is not None]
        return {
            "days": len(dataset.data),
            "max_high": max(temps_max) if temps_max else None,
            "min_low": min(temps_min) if temps_min else None,
            "avg_high": mean(temps_max) if temps_max else None,
            "avg_low": mean(temps_min) if temps_min else None,
            "avg_precip_probability": mean(precip) if precip else None,
        }

