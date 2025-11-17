import logging

from fastapi.testclient import TestClient

from app.main import app
from app.services.logging import RequestContext, request_log_store


client = TestClient(app)


def setup_function(_) -> None:
    request_log_store.clear()


def test_request_logs_endpoint_returns_entries() -> None:
    context = RequestContext()
    context.info(logging.getLogger(__name__), "synthetic milestone", event="test.event")

    response = client.get(f"/api/requests/{context.request_id}/logs")
    body = response.json()

    assert response.status_code == 200
    assert body["request_id"] == context.request_id
    assert len(body["logs"]) == 1
    assert body["logs"][0]["message"] == "synthetic milestone"
    assert body["logs"][0]["extra"]["event"] == "test.event"
