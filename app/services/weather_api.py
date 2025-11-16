"""HTTP clients for geocoding data."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

GEOCODER_URL = "https://geocoding-api.open-meteo.com/v1/search"


logger = logging.getLogger(__name__)


@dataclass
class GeocodeResult:
    name: str
    latitude: float
    longitude: float


class GeocodingService:
    """Thin wrapper around Open-Meteo's geocoding endpoint."""

    async def geocode(self, location: str) -> GeocodeResult:
        params = {"name": location, "count": 1}
        logger.debug("geocoding lookup", extra={"location": location})
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(GEOCODER_URL, params=params)
            response.raise_for_status()
        payload = response.json()
        first = payload.get("results", [{}])[0]
        if not first:
            raise ValueError(f"Could not geocode location: {location}")
        result = GeocodeResult(name=first.get("name", location), latitude=first["latitude"], longitude=first["longitude"])
        logger.info("geocoding success", extra={"location": result.name, "lat": result.latitude, "lon": result.longitude})
        return result
