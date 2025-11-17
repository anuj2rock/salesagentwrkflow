"""Helper that exposes the SatSource provider spec derived from the SRS."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from ...schemas import ProviderSpec


_BASE_SPEC: Dict[str, Any] = {
    "provider_id": "sat-source",
    "name": "SatSource Agronomic Intelligence",
    "version": "2024.06",
    "base_url": "https://api.satsource.ag",
    "auth": {
        "header_name": "api-key",
        "header_value_template": "{{api_key}}",
        "secrets": {},
    },
    "endpoints": [
        {
            "name": "Submit aggregation job (stable)",
            "method": "POST",
            "path": "/v2/reports",
            "description": (
                "Primary production endpoint for SatSource aggregation jobs. "
                "Accepts up to five regions per submission."
            ),
            "query_parameters": [],
            "body_parameters": [
                {
                    "name": "referenceId",
                    "type": "string",
                    "required": True,
                    "description": "Unique identifier provided by the caller to correlate callbacks.",
                },
                {
                    "name": "regionIds",
                    "type": "array",
                    "required": True,
                    "description": "List of 1-5 region IDs matching SatSource's registry.",
                },
                {
                    "name": "reportType",
                    "type": "string",
                    "required": True,
                    "description": (
                        "Enumeration of report scopes: seasonal, annual, or multi-year. "
                        "Multi-year submissions must also specify a valid yearCount."
                    ),
                },
                {
                    "name": "yearCount",
                    "type": "integer",
                    "required": False,
                    "description": (
                        "Total number of historical years to aggregate. "
                        "Valid range is 1-5 and values above 1 are only allowed for multi-year reports."
                    ),
                },
                {
                    "name": "timeframe",
                    "type": "object",
                    "required": True,
                    "description": "ISO-8601 start/end dates bounding the aggregation window.",
                },
                {
                    "name": "callbackUrl",
                    "type": "string",
                    "required": False,
                    "description": "HTTPS endpoint invoked when PDFs and narratives are ready.",
                },
            ],
        },
        {
            "name": "Submit aggregation job (beta)",
            "method": "POST",
            "path": "/beta/v2/reports",
            "description": (
                "Feature flag endpoint for the beta environment hosted at https://beta.api.satsource.ag. "
                "Shares the payload schema and enforces the same regional and yearCount constraints."
            ),
            "query_parameters": [],
            "body_parameters": [],
        },
    ],
    "callbacks": [
        {
            "event": "report.completed",
            "url_template": "https://agent.example.com/api/providers/sat-source/callback/{referenceId}",
            "payload_fields": [
                "referenceId",
                "status",
                "artifactUrl",
                "satScore",
                "metadata",
            ],
            "description": (
                "SatSource invokes this callback when report artifacts (PDF + metadata) are ready. "
                "Payload includes the referenceId along with satScore summaries so the agent "
                "can map asynchronous deliveries back to the originating request."
            ),
        }
    ],
}


def sat_source_provider_spec_payload(provider_id: str = "sat-source", api_key: str | None = None) -> Dict[str, Any]:
    """Return a mutable dict representing the SatSource spec payload."""

    spec = deepcopy(_BASE_SPEC)
    spec["provider_id"] = provider_id
    secrets: Dict[str, str] = {}
    if api_key:
        secrets = {"api_key": api_key}
    spec["auth"]["secrets"] = secrets
    return spec


def build_sat_source_provider_spec(provider_id: str = "sat-source", api_key: str | None = None) -> ProviderSpec:
    """Return a ``ProviderSpec`` model for SatSource."""

    payload = sat_source_provider_spec_payload(provider_id=provider_id, api_key=api_key)
    return ProviderSpec.model_validate(payload)


__all__ = [
    "build_sat_source_provider_spec",
    "sat_source_provider_spec_payload",
]
