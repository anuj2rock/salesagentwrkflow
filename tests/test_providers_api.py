from fastapi.testclient import TestClient

from app.main import app
from app.services.provider_registry import provider_registry
from app.services.providers.sat_source_spec import sat_source_provider_spec_payload

client = TestClient(app)


def setup_function(_) -> None:
    provider_registry.clear()


def _provider_payload(provider_id: str = "sat-source") -> dict:
    payload = sat_source_provider_spec_payload(api_key="super-secret-key")
    payload["provider_id"] = provider_id
    return payload


def test_register_provider_masks_secrets() -> None:
    response = client.post("/api/providers", json=_provider_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["provider_id"] == "sat-source"
    assert "secrets" not in body["auth"]
    assert body["auth"]["has_secrets"] is True


def test_get_provider_returns_sanitized_payload() -> None:
    client.post("/api/providers", json=_provider_payload())
    response = client.get("/api/providers/sat-source")
    assert response.status_code == 200
    body = response.json()
    assert body["auth"]["has_secrets"] is True
    assert "secrets" not in body["auth"]


def test_get_missing_provider_returns_404() -> None:
    response = client.get("/api/providers/unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Provider not found"
