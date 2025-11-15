"""Pydantic schemas shared across the weather report POC."""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class Timeframe(BaseModel):
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class WeatherSpec(BaseModel):
    """Structured representation of a natural-language weather prompt."""

    location: Location
    timeframe: Timeframe
    metrics: List[str]
    units: Literal["metric", "imperial"] = "metric"
    narrative_tone: Literal["business", "casual"] = "business"


class WeatherPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    delivery: Literal["inline", "link"] = "inline"


class WeatherDataPoint(BaseModel):
    date: date
    temperature_max: Optional[float] = None
    temperature_min: Optional[float] = None
    precipitation_probability: Optional[float] = None


class WeatherDataset(BaseModel):
    source: str
    granularity: Literal["daily"] = "daily"
    data: List[WeatherDataPoint]


class Narrative(BaseModel):
    title: str
    summary: str


class WeatherReportPayload(BaseModel):
    request: WeatherSpec
    dataset: WeatherDataset
    narrative: Narrative

