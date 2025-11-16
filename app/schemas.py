"""Pydantic schemas shared across the weather report POC."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, SecretStr


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


class AuthConfig(BaseModel):
    """Authentication configuration for upstream provider APIs."""

    header_name: str = Field(..., min_length=1)
    header_value_template: str = Field(
        ...,
        min_length=1,
        description="Template that may reference secrets such as {{api_key}}",
    )
    secrets: Dict[str, SecretStr] = Field(
        default_factory=dict,
        description="Map of secret names to actual secret values.",
    )


class RequestParameter(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean", "object", "array"] = "string"
    required: bool = False
    description: Optional[str] = None


class EndpointConfig(BaseModel):
    name: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(..., min_length=1)
    description: Optional[str] = None
    query_parameters: List[RequestParameter] = Field(default_factory=list)
    body_parameters: List[RequestParameter] = Field(default_factory=list)


class CallbackExpectation(BaseModel):
    event: str = Field(..., description="Trigger for the callback, e.g. job.completed")
    url_template: Optional[str] = Field(
        default=None,
        description="Endpoint the provider will call when the event fires.",
    )
    payload_fields: List[str] = Field(
        default_factory=list,
        description="Expected fields included in the callback payload.",
    )
    description: Optional[str] = None


class ProviderSpec(BaseModel):
    provider_id: str = Field(..., min_length=3, max_length=100)
    name: str
    version: Optional[str] = Field(default=None, description="Version of the provider spec")
    base_url: HttpUrl
    auth: AuthConfig
    endpoints: List[EndpointConfig]
    callbacks: List[CallbackExpectation] = Field(default_factory=list)

    def sanitized_dict(self) -> Dict[str, object]:
        """Return a dictionary without sensitive fields such as secrets."""

        data = self.model_dump()
        secrets = data.get("auth", {}).pop("secrets", None)
        if secrets is not None:
            data["auth"]["has_secrets"] = bool(secrets)
        return data

