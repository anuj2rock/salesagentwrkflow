"""Functional tests that exercise the SatSource provider HTTP flow."""

import asyncio
from datetime import date
from typing import Any, Dict

import httpx
import pytest

from app.schemas import Location, ReportSpec, Timeframe
from app.services.logging import RequestContext, request_log_store
from app.services.providers import ProviderRequestError, SatSourceProvider
from app.services.providers.sat_source import callback_registry


def _build_spec() -> ReportSpec:
    return ReportSpec(
        location=Location(name="region:r1|r2", latitude=30.0, longitude=-97.0),
        timeframe=Timeframe(start=date(2024, 5, 1), end=date(2024, 5, 2)),
        metrics=["satScore", "precipitationProbability"],
        units="metric",
        provider_id="sat-source",
        reference_id="req-555",
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    callback_registry.clear()
    request_log_store.clear()


@pytest.mark.usefixtures("_reset_state")
def test_sat_source_success_flow_logs_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SatSourceProvider(
        provider_id="sat-source",
        config={"callback_url": "https://agent.example/callback/{referenceId}"},
        secrets={"api_key": "secret"},
    )
    spec = _build_spec()

    response_payload: Dict[str, Any] = {
        "referenceId": spec.reference_id,
        "metadata": {"sourceId": "sat-source/prod"},
        "farmDetails": [
            {
                "metadata": {"reportDate": "2024-05-01"},
                "satScore": {
                    "temperature": {"max": 30, "min": 20},
                    "precipitationProbability": 0.6,
                },
            }
        ],
        "callback": {
            "referenceId": spec.reference_id,
            "status": "pending",
            "artifactUrl": "https://files.example/ref-555.pdf",
        },
    }

    async def fake_post(self, url: str, json: dict, headers: dict) -> httpx.Response:  # type: ignore[override]
        assert headers["api-key"] == "secret"
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=response_payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    context = RequestContext(request_id="req-success").with_provider("sat-source")
    dataset = _run(provider.fetch(spec, context=context))

    assert dataset.data[0].temperature_max == 30
    expected_callback = provider.config["callback_url"].replace("{referenceId}", spec.reference_id)
    stored_callback = callback_registry.get(expected_callback)
    assert stored_callback is not None
    assert stored_callback["reference_id"] == spec.reference_id
    logs = request_log_store.get(context.request_id)
    assert any(entry["extra"].get("event") == "provider.dispatch" and entry["extra"].get("payload_bytes") for entry in logs)
    assert any(entry["extra"].get("event") == "provider.callback_status" for entry in logs)


@pytest.mark.usefixtures("_reset_state")
def test_sat_source_sync_error_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SatSourceProvider(provider_id="sat-source", config={}, secrets={"api_key": "secret"})
    spec = _build_spec()

    async def fake_post(self, url: str, json: dict, headers: dict) -> httpx.Response:  # type: ignore[override]
        request = httpx.Request("POST", url)
        return httpx.Response(
            400,
            json={"errors": [{"code": "R001", "message": "invalid region", "caseId": 7}]},
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    context = RequestContext(request_id="req-error").with_provider("sat-source")
    with pytest.raises(ProviderRequestError):
        _run(provider.fetch(spec, context=context))

    logs = request_log_store.get(context.request_id)
    assert any(entry["extra"].get("event") == "provider.sync_error" for entry in logs)
