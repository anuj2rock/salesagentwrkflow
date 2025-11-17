"""Registry that describes which provider client to instantiate for a provider ID."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Type

from .base import BaseProviderClient
from .open_meteo import OpenMeteoProvider
from .sat_source import DEFAULT_ENDPOINT, SatSourceProvider


@dataclass
class ProviderRegistryEntry:
    client: Type[BaseProviderClient]
    config: Mapping[str, Any]
    secrets: Mapping[str, Any]


def load_default_registry() -> Dict[str, ProviderRegistryEntry]:
    sat_source_api_key = os.getenv("SAT_SOURCE_API_KEY")
    sat_source_max_regions = int(os.getenv("SAT_SOURCE_MAX_REGIONS", "5"))
    sat_source_endpoint = os.getenv("SAT_SOURCE_ENDPOINT", DEFAULT_ENDPOINT)
    sat_source_beta_endpoint = os.getenv("SAT_SOURCE_BETA_ENDPOINT")
    sat_source_callback = os.getenv("SAT_SOURCE_CALLBACK_URL")
    sat_source_report_type = os.getenv("SAT_SOURCE_REPORT_TYPE", "seasonal")
    sat_source_year_count_raw = os.getenv("SAT_SOURCE_YEAR_COUNT", "1")
    try:
        sat_source_year_count = int(sat_source_year_count_raw)
    except ValueError:
        sat_source_year_count = 1
    return {
        "open-meteo": ProviderRegistryEntry(
            client=OpenMeteoProvider,
            config={"weather_url": os.getenv("OPEN_METEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")},
            secrets={},
        ),
        "sat-source": ProviderRegistryEntry(
            client=SatSourceProvider,
            config={
                "endpoint": sat_source_endpoint,
                "beta_endpoint": sat_source_beta_endpoint,
                "max_region_ids": sat_source_max_regions,
                "report_type": sat_source_report_type,
                "year_count": sat_source_year_count,
                "callback_url": sat_source_callback,
            },
            secrets={"api_key": sat_source_api_key} if sat_source_api_key else {},
        ),
    }
