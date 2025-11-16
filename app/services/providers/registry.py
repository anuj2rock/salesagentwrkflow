"""Registry that describes which provider client to instantiate for a provider ID."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Type

from .base import BaseProviderClient
from .open_meteo import OpenMeteoProvider
from .sat_source import SatSourceProvider


@dataclass
class ProviderRegistryEntry:
    client: Type[BaseProviderClient]
    config: Mapping[str, Any]
    secrets: Mapping[str, Any]


def load_default_registry() -> Dict[str, ProviderRegistryEntry]:
    sat_source_api_key = os.getenv("SAT_SOURCE_API_KEY")
    return {
        "open-meteo": ProviderRegistryEntry(
            client=OpenMeteoProvider,
            config={"weather_url": os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")},
            secrets={},
        ),
        "sat-source": ProviderRegistryEntry(
            client=SatSourceProvider,
            config={
                "endpoint": os.getenv("SAT_SOURCE_ENDPOINT", "https://api.satsource.example/v1/reports"),
                "max_region_ids": 5,
            },
            secrets={"api_key": sat_source_api_key} if sat_source_api_key else {},
        ),
    }
