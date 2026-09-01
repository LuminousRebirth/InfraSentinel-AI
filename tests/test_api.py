from __future__ import annotations

from fastapi.testclient import TestClient

from infrasentinel.health import DependencyHealth, ReadinessResponse
from infrasentinel.main import app


def test_root_redirects_to_api_docs() -> None:
    response = TestClient(app).get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


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
