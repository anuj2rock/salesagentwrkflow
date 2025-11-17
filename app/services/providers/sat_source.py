"""SatSource provider client that wraps the satellite aggregation POST endpoint."""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

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
ALLOWED_REPORT_TYPES = {"seasonal", "annual", "multi-year"}


class CallbackRegistry:
    """Simple registry used to correlate callback URLs with request IDs."""

    def __init__(self) -> None:
        self._records: MutableMapping[str, Mapping[str, str]] = {}

    def record(self, callback_url: str, *, request_id: str, provider_id: str, reference_id: str) -> None:
        if callback_url:
            self._records[callback_url] = {
                "request_id": request_id,
                "provider_id": provider_id,
                "reference_id": reference_id,
            }

    def get(self, callback_url: str) -> Mapping[str, str] | None:
        return self._records.get(callback_url)

    def clear(self) -> None:
        self._records.clear()


callback_registry = CallbackRegistry()


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
        report_type = self._resolve_report_type()
        year_count = self._resolve_year_count(report_type)

        payload: dict[str, Any] = {
            "referenceId": reference_id,
            "regionIds": region_ids,
            "metrics": spec.metrics,
            "timeframe": {
                "start": spec.timeframe.start.isoformat(),
                "end": spec.timeframe.end.isoformat(),
            },
            "units": spec.units,
            "reportType": report_type,
            "yearCount": year_count,
        }
        callback_template = self.config.get("callback_url")
        callback_url = self._render_callback_url(callback_template, reference_id, context)
        if callback_url:
            payload["callbackUrl"] = callback_url
            if context:
                context.info(
                    logger,
                    "SatSource callback scheduled",
                    event="provider.callback_scheduled",
                    callback_url=callback_url,
                )
            callback_registry.record(
                callback_url,
                request_id=context.request_id if context else reference_id,
                provider_id=self.provider_id,
                reference_id=reference_id,
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
            headers["api-key"] = str(api_key)
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
        payload_bytes = len(json.dumps(payload_dict, default=str))
        log_fields: Dict[str, Any] = {
            "event": "provider.dispatch",
            "regions": payload_dict.get("regionIds"),
            "reference_id": spec.reference_id,
            "payload_bytes": payload_bytes,
            "endpoint": url,
        }
        if context:
            context.info(logger, "sending SatSource request", **log_fields)
        else:
            logger.info("sending SatSource request", extra={"provider_id": self.provider_id, **log_fields})
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload_dict, headers=dict(request.headers or {}))
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            message = self._summarize_http_error(exc.response)
            if context:
                context.warning(
                    logger,
                    "SatSource HTTP error",
                    event="provider.sync_error",
                    reference_id=spec.reference_id,
                    status_code=exc.response.status_code,
                    error=message,
                )
            raise ProviderRequestError(message) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network plumbing
            raise ProviderRequestError(str(exc)) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderRequestError("SatSource returned an invalid JSON payload") from exc
        self._raise_for_sync_error(payload, spec, context=context)
        return payload

    def parse_response(
        self,
        payload: Mapping[str, Any],
        spec: ReportSpec,
        context: RequestContext | None = None,
    ) -> ProviderDataset:
        callback_payload = self._extract_callback_payload(payload)
        if context and callback_payload:
            self._log_callback_status(callback_payload, spec, context)
        dataset_payload = self._extract_dataset_payload(payload)
        if not dataset_payload:
            raise ProviderRequestError("SatSource response did not include dataset content")
        metadata = dataset_payload.get("metadata") or payload.get("metadata")
        source = (
            dataset_payload.get("source")
            or (metadata.get("sourceId") if isinstance(metadata, Mapping) else None)
            or payload.get("source")
            or "sat-source"
        )
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

    def _extract_callback_payload(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        callback = payload.get("callback") or payload.get("callbackPayload")
        if isinstance(callback, Mapping):
            return callback
        return None

    def _extract_dataset_payload(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if not isinstance(payload, Mapping):
            return None
        dataset = payload.get("dataset") or payload.get("data")
        if dataset:
            return dataset if isinstance(dataset, Mapping) else {"records": dataset}
        farm_details = payload.get("farmDetails")
        if isinstance(farm_details, list):
            return {"records": farm_details, "metadata": payload.get("metadata"), "source": payload.get("source")}
        callback = self._extract_callback_payload(payload)
        if isinstance(callback, Mapping):
            inner = callback.get("dataset") or callback.get("body") or callback.get("payload")
            if isinstance(inner, Mapping):
                return inner
        return None

    def _parse_record(self, record: Mapping[str, Any]) -> WeatherDataPoint:
        day = record.get("date") or record.get("day")
        metadata = record.get("metadata")
        if not day and isinstance(metadata, Mapping):
            day = metadata.get("reportDate") or metadata.get("collectedAt") or metadata.get("deliveredAt")
        if not day:
            raise ProviderRequestError("SatSource record missing date field")
        current_date = self._coerce_date(day)
        sat_score = record.get("satScore") if isinstance(record.get("satScore"), Mapping) else None
        precip = record.get("precipitation_probability") or record.get("precipProbability")
        temp_max = record.get("temperature_max") or record.get("temperatureMax") or record.get("maxTemp")
        temp_min = record.get("temperature_min") or record.get("temperatureMin") or record.get("minTemp")
        if sat_score:
            if isinstance(sat_score.get("temperature"), Mapping):
                temp_max = temp_max or sat_score["temperature"].get("max") or sat_score["temperature"].get("high")
                temp_min = temp_min or sat_score["temperature"].get("min") or sat_score["temperature"].get("low")
            else:
                temp_max = temp_max or sat_score.get("temperatureMax") or sat_score.get("maxTemp")
                temp_min = temp_min or sat_score.get("temperatureMin") or sat_score.get("minTemp")
            precip = precip or sat_score.get("precipitationProbability") or sat_score.get("precipProbability")
        precip = self._normalize_precip(precip)
        return WeatherDataPoint(
            date=current_date,
            temperature_max=_maybe_float(temp_max),
            temperature_min=_maybe_float(temp_min),
            precipitation_probability=precip,
        )

    def _render_callback_url(
        self,
        template: Any,
        reference_id: str,
        context: RequestContext | None,
    ) -> str | None:
        if not template:
            return None
        template_str = str(template)
        replacements = {
            "referenceId": reference_id,
            "requestId": context.request_id if context else "",
            "providerId": self.provider_id,
        }
        try:
            return template_str.format(**replacements)
        except Exception:
            return template_str

    def _resolve_report_type(self) -> str:
        report_type = str(self.config.get("report_type", "seasonal")).strip().lower()
        if report_type not in ALLOWED_REPORT_TYPES:
            raise ProviderConfigurationError(
                f"Unsupported SatSource report_type '{report_type}'. Allowed values: {sorted(ALLOWED_REPORT_TYPES)}"
            )
        return report_type

    def _resolve_year_count(self, report_type: str) -> int:
        raw = self.config.get("year_count", 1)
        try:
            year_count = int(raw)
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError("SatSource year_count must be an integer") from exc
        if report_type == "multi-year":
            if year_count < 2 or year_count > 5:
                raise ProviderRequestError("SatSource multi-year reports require a yearCount between 2 and 5 years")
        else:
            if year_count != 1:
                raise ProviderRequestError("yearCount must be 1 for seasonal or annual SatSource reports")
        return year_count

    def _collect_errors(self, payload: Any) -> List[str]:
        messages: List[str] = []
        if isinstance(payload, Mapping):
            if error := payload.get("error"):
                messages.extend(self._format_error(error))
            if errors := payload.get("errors"):
                if isinstance(errors, Sequence):
                    for err in errors:
                        messages.extend(self._format_error(err))
                else:
                    messages.extend(self._format_error(errors))
            if payload.get("errorCode") or payload.get("message"):
                messages.extend(self._format_error(payload))
        elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            for item in payload:
                messages.extend(self._format_error(item))
        elif isinstance(payload, str):
            messages.append(payload)
        return [message for message in messages if message]

    def _format_error(self, error: Any) -> List[str]:
        if isinstance(error, Mapping):
            parts = []
            code = error.get("code") or error.get("errorCode")
            detail = error.get("message") or error.get("detail") or error.get("reason")
            case_id = error.get("case") or error.get("caseId")
            field = error.get("field") or error.get("path")
            if code:
                parts.append(str(code))
            if detail:
                parts.append(str(detail))
            if case_id:
                parts.append(f"case {case_id}")
            if field:
                parts.append(f"field {field}")
            if parts:
                return [" | ".join(parts)]
            return [str(error)]
        if isinstance(error, str):
            return [error]
        return [str(error)] if error is not None else []

    def _summarize_http_error(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if payload is not None:
            errors = self._collect_errors(payload)
            if errors:
                return "; ".join(errors)
        return f"SatSource returned HTTP {response.status_code}"

    def _raise_for_sync_error(
        self,
        payload: Mapping[str, Any] | Sequence[Any] | str,
        spec: ReportSpec,
        context: RequestContext | None = None,
    ) -> None:
        errors = self._collect_errors(payload)
        if not errors:
            return
        message = "; ".join(errors)
        if context:
            context.warning(
                logger,
                "SatSource rejected the payload",
                event="provider.sync_error",
                reference_id=spec.reference_id,
                errors=errors,
            )
        raise ProviderRequestError(message)

    def _log_callback_status(
        self,
        callback_payload: Mapping[str, Any],
        spec: ReportSpec,
        context: RequestContext,
    ) -> None:
        context.info(
            logger,
            "SatSource callback payload received",
            event="provider.callback_status",
            reference_id=callback_payload.get("referenceId") or spec.reference_id,
            callback_status=callback_payload.get("status"),
            artifact_url=callback_payload.get("artifactUrl"),
        )

    def _coerce_date(self, value: Any) -> date:
        if isinstance(value, date):
            return value
        text = str(value)
        if "T" in text:
            text = text.split("T", 1)[0]
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ProviderRequestError(f"Invalid date value in SatSource payload: {value}") from exc

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
