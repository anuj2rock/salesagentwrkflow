"""Generate a lightweight narrative summary for the PDF."""
from __future__ import annotations

from statistics import mean

from ..schemas import Narrative, WeatherDataset


def build_narrative(dataset: WeatherDataset) -> Narrative:
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

