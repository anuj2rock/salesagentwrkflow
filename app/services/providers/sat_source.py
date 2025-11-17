"""SatSource provider client that wraps the satellite aggregation POST endpoint."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable, List, Mapping

import httpx

from ...schemas import ProviderDataset, ReportSpec, WeatherDataPoint
from ..logging import RequestContext
from .base import (
    BaseProviderClient,
    ProviderConfigurationError,
    ProviderRequestError,
    SignedRequest,
)

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.satsource.example/v1/reports"


class SatSourceProvider(BaseProviderClient):
    """Client that POSTs report specs to the SatSource ingestion endpoint."""

    def build_payload(self, spec: ReportSpec, context: RequestContext | None = None) -> Mapping[str, Any]:
        region_ids = self._resolve_region_ids(spec)
        max_regions = int(self.config.get("max_region_ids", 5))
        if not region_ids:
            raise ProviderRequestError("At least one regionId is required for SatSource requests")
        if len(region_ids) > max_regions:
            raise ProviderRequestError(f"SatSource supports at most {max_regions} region IDs")
        reference_id = spec.reference_id
        if not reference_id:
            raise ProviderRequestError("SatSource requests require a referenceId")

        payload: dict[str, Any] = {
            "referenceId": reference_id,
            "regionIds": region_ids,
            "metrics": spec.metrics,
            "timeframe": {
                "start": spec.timeframe.start.isoformat(),
                "end": spec.timeframe.end.isoformat(),
            },
            "units": spec.units,
        }
        if callback := self.config.get("callback_url"):
            payload["callbackUrl"] = callback
            if context:
                context.info(
                    logger,
                    "SatSource callback scheduled",
                    event="provider.callback_scheduled",
                    callback_url=callback,
                )
        return payload

    def sign_request(
        self,
        payload: Mapping[str, Any],
        spec: ReportSpec,
        context: RequestContext | None = None,
    ) -> SignedRequest:
        api_key = self.secrets.get("api_key")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return SignedRequest(payload=payload, headers=headers)

    async def dispatch(
        self,
        request: SignedRequest,
        spec: ReportSpec,
        context: RequestContext | None = None,
    ) -> Mapping[str, Any]:
        url = self.config.get("endpoint", DEFAULT_ENDPOINT)
        timeout = self.config.get("timeout", 20)
        payload_dict = dict(request.payload)
        if context:
            context.info(
                logger,
                "sending SatSource request",
                event="provider.dispatch",
                regions=payload_dict.get("regionIds"),
                reference_id=spec.reference_id,
            )
        else:
            logger.info(
                "sending SatSource request",
                extra={
                    "provider_id": self.provider_id,
                    "regions": payload_dict.get("regionIds"),
                    "reference_id": spec.reference_id,
                },
            )
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload_dict, headers=dict(request.headers or {}))
            response.raise_for_status()
        return response.json()

    def parse_response(
        self,
        payload: Mapping[str, Any],
        spec: ReportSpec,
        context: RequestContext | None = None,
    ) -> ProviderDataset:
        dataset_payload = self._extract_dataset_payload(payload)
        if not dataset_payload:
            raise ProviderRequestError("SatSource response did not include dataset content")
        source = dataset_payload.get("source") or payload.get("source") or "sat-source"
        records: Iterable[Mapping[str, Any]] = dataset_payload.get("records") or dataset_payload.get("data") or []
        data_points = [self._parse_record(record) for record in records]
        if context:
            context.info(
                logger,
                "SatSource dataset normalized",
                event="provider.dataset_parsed",
                records=len(data_points),
            )
        else:
            logger.info(
                "SatSource dataset normalized",
                extra={"provider_id": self.provider_id, "records": len(data_points)},
            )
        return ProviderDataset(provider_id=self.provider_id, source=source, data=data_points)

    def _resolve_region_ids(self, spec: ReportSpec) -> List[str]:
        if region_ids := self.config.get("region_ids"):
            if not isinstance(region_ids, list):
                raise ProviderConfigurationError("registry region_ids must be a list")
            return [str(region).strip() for region in region_ids if str(region).strip()]

        name = (spec.location.name or "").strip()
        if not name:
            return []
        lowered = name.lower()
        delimiters = ["|", ";"]
        if lowered.startswith("region:"):
            name = name.split(":", 1)[1]
            delimiters.append(",")
        for delimiter in delimiters:
            if delimiter in name:
                parts = [part.strip() for part in name.split(delimiter)]
                return [part for part in parts if part]
        return [name]

    def _extract_dataset_payload(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if not isinstance(payload, Mapping):
            return None
        dataset = payload.get("dataset") or payload.get("data")
        if dataset:
            return dataset if isinstance(dataset, Mapping) else {"records": dataset}
        callback = payload.get("callback") or payload.get("callbackPayload")
        if isinstance(callback, Mapping):
            inner = callback.get("dataset") or callback.get("body") or callback.get("payload")
            if isinstance(inner, Mapping):
                return inner
        return None

    def _parse_record(self, record: Mapping[str, Any]) -> WeatherDataPoint:
        day = record.get("date") or record.get("day")
        if not day:
            raise ProviderRequestError("SatSource record missing date field")
        current_date = date.fromisoformat(str(day))
        precip = self._normalize_precip(record.get("precipitation_probability") or record.get("precipProbability"))
        temp_max = record.get("temperature_max") or record.get("temperatureMax") or record.get("maxTemp")
        temp_min = record.get("temperature_min") or record.get("temperatureMin") or record.get("minTemp")
        return WeatherDataPoint(
            date=current_date,
            temperature_max=_maybe_float(temp_max),
            temperature_min=_maybe_float(temp_min),
            precipitation_probability=precip,
        )

    def _normalize_precip(self, value: Any) -> float | None:
        if value is None:
            return None
        numeric = _maybe_float(value)
        if numeric is None:
            return None
        if 0 <= numeric <= 1:
            return numeric * 100
        return numeric


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
