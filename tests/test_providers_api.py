from fastapi.testclient import TestClient

from app.main import app
from app.services.provider_registry import provider_registry

client = TestClient(app)


def setup_function(_) -> None:
    provider_registry.clear()


def _provider_payload(provider_id: str = "sat-source") -> dict:
    return {
        "provider_id": provider_id,
        "name": "SatSource",
        "version": "2023.10",
        "base_url": "https://api.satsource.example.com",
        "auth": {
            "header_name": "Authorization",
            "header_value_template": "Bearer {{api_key}}",
            "secrets": {"api_key": "super-secret-key"},
        },
        "endpoints": [
            {
                "name": "Submit task",
                "method": "POST",
                "path": "/v1/tasks",
                "description": "Create a new sat task",
                "query_parameters": [],
                "body_parameters": [
                    {"name": "region", "type": "string", "required": True},
                    {"name": "start_date", "type": "string", "required": True},
                ],
            }
        ],
        "callbacks": [
            {
                "event": "task.completed",
                "url_template": "https://agent.example.com/callback/{task_id}",
                "payload_fields": ["task_id", "status"],
                "description": "Called when a task is completed",
            }
        ],
    }


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
