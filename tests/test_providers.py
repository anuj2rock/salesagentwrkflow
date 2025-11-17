"""Unit tests for provider client helpers."""

from datetime import date

import pytest

from app.schemas import Location, ReportSpec, Timeframe
from app.services.providers import ProviderRequestError, SatSourceProvider
from app.services.providers.sat_source import callback_registry


def _build_spec(location_name: str = "region:r1|r2") -> ReportSpec:
    return ReportSpec(
        location=Location(name=location_name, latitude=30.0, longitude=-97.0),
        timeframe=Timeframe(start=date(2024, 5, 1), end=date(2024, 5, 3)),
        metrics=["temperature_max", "temperature_min", "precipitation_probability"],
        units="metric",
        provider_id="sat-source",
        reference_id="req-123",
    )


def setup_function(_) -> None:
    callback_registry.clear()


def test_sat_source_rejects_too_many_regions() -> None:
    provider = SatSourceProvider(provider_id="sat-source", config={"max_region_ids": 5}, secrets={})
    spec = _build_spec(location_name="region:r1|r2|r3|r4|r5|r6")

    try:
        provider.build_payload(spec)
    except ProviderRequestError as exc:
        assert "at most" in str(exc)
    else:  # pragma: no cover
        assert False, "expected ProviderRequestError"


def test_sat_source_enforces_year_count_for_multi_year() -> None:
    provider = SatSourceProvider(
        provider_id="sat-source",
        config={"report_type": "multi-year", "year_count": 1},
        secrets={}
    )
    spec = _build_spec()

    with pytest.raises(ProviderRequestError):
        provider.build_payload(spec)


def test_sat_source_parses_sync_dataset() -> None:
    provider = SatSourceProvider(provider_id="sat-source", config={}, secrets={})
    spec = _build_spec()
    payload = {
        "dataset": {
            "source": "sat-source",
            "records": [
                {
                    "date": "2024-05-01",
                    "temperatureMax": 25,
                    "temperatureMin": 10,
                    "precipProbability": 0.5,
                }
            ],
        }
    }

    dataset = provider.parse_response(payload, spec)

    assert dataset.provider_id == "sat-source"
    assert dataset.data[0].temperature_max == 25
    assert dataset.data[0].precipitation_probability == 50


def test_sat_source_parses_callback_dataset() -> None:
    provider = SatSourceProvider(provider_id="sat-source", config={}, secrets={})
    spec = _build_spec()
    payload = {
        "farmDetails": [
            {
                "metadata": {"reportDate": "2024-05-02"},
                "satScore": {
                    "temperature": {"max": 22.4, "min": 9.2},
                    "precipitationProbability": 0.8,
                },
            }
        ]
    }

    dataset = provider.parse_response(payload, spec)

    assert dataset.data[0].temperature_min == 9.2
    assert dataset.data[0].precipitation_probability == 80


def test_sat_source_records_callback_registry() -> None:
    provider = SatSourceProvider(
        provider_id="sat-source",
        config={"callback_url": "https://agent.example/cb/{referenceId}"},
        secrets={},
    )
    spec = _build_spec()

    payload = provider.build_payload(spec)

    assert payload["callbackUrl"].endswith(spec.reference_id)
    stored = callback_registry.get(payload["callbackUrl"])
    assert stored["reference_id"] == spec.reference_id
