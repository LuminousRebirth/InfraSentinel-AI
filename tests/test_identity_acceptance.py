from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from infrasentinel.database import SessionLocal, get_engine
from infrasentinel.main import app
from infrasentinel.services import bootstrap_admin

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def test_complete_identity_access_lifecycle() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_password = "admin correct horse battery"
    user_password = "user correct horse battery"
    new_password = "new correct horse battery"
    admin_name = f"accept-admin-{suffix}"
    user_name = f"accept-user-{suffix}"

    with SessionLocal(bind=get_engine()) as db:
        bootstrap_admin(
            db,
            email=f"{admin_name}@example.com",
            username=admin_name,
            password=admin_password,
            display_name="Acceptance Administrator",
            locale="en",
        )

    anonymous = TestClient(app, client=(f"acceptance-{suffix}", 50000))
    registered = anonymous.post(
        "/api/v1/auth/register",
        json={
            "email": f"{user_name}@example.com",
            "username": user_name,
            "display_name": "Acceptance User",
            "password": user_password,
            "locale": "zh-CN",
        },
    )
    assert registered.status_code == 201
    user_id = registered.json()["id"]
    assert (
        anonymous.post(
            "/api/v1/auth/login", json={"identifier": user_name, "password": user_password}
        ).json()["error"]["code"]
        == "auth.pending"
    )

    admin = TestClient(app, client=(f"admin-{suffix}", 50001))
    assert (
        admin.post(
            "/api/v1/auth/login", json={"identifier": admin_name, "password": admin_password}
        ).status_code
        == 200
    )
    assert (
        admin.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"status": "enabled"},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    project = admin.post(
        "/api/v1/admin/projects",
        json={"code": f"A-{suffix}", "name": "Acceptance Pipeline"},
        headers=ORIGIN,
    ).json()
    unassigned_project = admin.post(
        "/api/v1/admin/projects",
        json={"code": f"B-{suffix}", "name": "Unassigned Pipeline"},
        headers=ORIGIN,
    ).json()
    assert (
        admin.put(
            f"/api/v1/admin/users/{user_id}/projects/{project['id']}", headers=ORIGIN
        ).status_code
        == 204
    )

    user = TestClient(app, client=(f"user-{suffix}", 50002))
    assert (
        user.post(
            "/api/v1/auth/login", json={"identifier": user_name, "password": user_password}
        ).status_code
        == 200
    )
    visible_project_ids = [item["id"] for item in user.get("/api/v1/projects").json()]
    assert visible_project_ids == [project["id"]]
    assert unassigned_project["id"] not in visible_project_ids
    assert (
        user.patch("/api/v1/auth/me", json={"locale": "en"}, headers=ORIGIN).json()["locale"]
        == "en"
    )
    assert (
        user.post(
            "/api/v1/auth/change-password",
            json={"current_password": user_password, "new_password": new_password},
            headers=ORIGIN,
        ).status_code
        == 204
    )
    assert user.get("/api/v1/auth/me").status_code == 401
    assert (
        user.post(
            "/api/v1/auth/login", json={"identifier": user_name, "password": new_password}
        ).status_code
        == 200
    )

    assert (
        admin.patch(
            f"/api/v1/admin/users/{user_id}/status",
            json={"status": "disabled"},
            headers=ORIGIN,
        ).status_code
        == 200
    )
    assert user.get("/api/v1/auth/me").status_code == 401
    audits = admin.get("/api/v1/admin/audit-events?limit=200").json()
    actions = {event["action"] for event in audits if event["target_id"] == user_id}
    assert {"auth.register", "admin.user_status", "auth.password_change"} <= actions
