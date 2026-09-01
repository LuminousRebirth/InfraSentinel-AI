from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from infrasentinel.database import SessionLocal, get_engine
from infrasentinel.main import app
from infrasentinel.services import bootstrap_admin

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def _admin_client(suffix: str) -> TestClient:
    email = f"api-admin-{suffix}@example.com"
    username = f"api-admin-{suffix}"
    password = "correct horse battery staple"
    with SessionLocal(bind=get_engine()) as db:
        bootstrap_admin(
            db,
            email=email,
            username=username,
            password=password,
            display_name="API Admin",
            locale="zh-CN",
        )
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login", json={"identifier": username, "password": password}
    )
    assert response.status_code == 200
    assert response.cookies.get("infrasentinel_session")
    return client


def test_register_approve_login_and_disable() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin = _admin_client(suffix)
    user = TestClient(app)
    username = f"api-user-{suffix}"
    password = "correct horse battery staple"

    registered = user.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "display_name": "API User",
            "password": password,
            "locale": "en",
        },
    )
    assert registered.status_code == 201
    user_id = registered.json()["id"]
    assert registered.json()["status"] == "pending"

    pending_login = user.post(
        "/api/v1/auth/login", json={"identifier": username, "password": password}
    )
    assert pending_login.status_code == 403
    assert pending_login.json()["error"]["code"] == "auth.pending"

    approved = admin.patch(
        f"/api/v1/admin/users/{user_id}/status",
        json={"status": "enabled"},
        headers=ORIGIN,
    )
    assert approved.status_code == 200

    logged_in = user.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    assert logged_in.status_code == 200
    assert user.get("/api/v1/auth/me").json()["username"] == username

    disabled = admin.patch(
        f"/api/v1/admin/users/{user_id}/status",
        json={"status": "disabled"},
        headers=ORIGIN,
    )
    assert disabled.status_code == 200
    assert user.get("/api/v1/auth/me").status_code == 401
