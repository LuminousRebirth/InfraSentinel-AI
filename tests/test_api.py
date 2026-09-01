from __future__ import annotations

from fastapi.testclient import TestClient

from infrasentinel.health import DependencyHealth, ReadinessResponse
from infrasentinel.main import app


def test_root_and_deep_link_serve_web_ui() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert client.get("/admin/users").status_code == 200
    assert client.get("/docs").status_code == 200


def test_unknown_api_route_remains_an_api_404() -> None:
    response = TestClient(app).get("/api/v1/not-real")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http.not_found"


def test_liveness() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_503_when_dependency_is_unavailable(monkeypatch) -> None:
    result = ReadinessResponse(
        status="degraded",
        dependencies={"postgresql": DependencyHealth(status="unavailable")},
    )
    monkeypatch.setattr("infrasentinel.api.readiness", lambda: result)

    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
