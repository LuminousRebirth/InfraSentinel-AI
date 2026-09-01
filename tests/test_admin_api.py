from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from infrasentinel.database import SessionLocal, get_engine
from infrasentinel.main import app
from infrasentinel.schemas import RegisterRequest, UserStatusUpdate
from infrasentinel.services import bootstrap_admin, register_user, update_user_status

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def test_project_scope_audit_and_admin_lifecycle() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_password = "correct horse battery staple"
    user_password = "another correct horse password"
    with SessionLocal(bind=get_engine()) as db:
        admin_user, _ = bootstrap_admin(
            db,
            email=f"scope-admin-{suffix}@example.com",
            username=f"scope-admin-{suffix}",
            password=admin_password,
            display_name="Scope Admin",
            locale="en",
        )
        normal_user = register_user(
            db,
            RegisterRequest(
                email=f"scope-user-{suffix}@example.com",
                username=f"scope-user-{suffix}",
                display_name="Scope User",
                password=user_password,
                locale="en",
            ),
            source_ip="127.0.0.1",
            user_agent="pytest",
        )
        update_user_status(
            db,
            actor=admin_user,
            target=normal_user,
            payload=UserStatusUpdate(status="enabled"),
            source_ip="127.0.0.1",
            user_agent="pytest",
        )
        normal_user_id = normal_user.id

    admin = TestClient(app)
    assert (
        admin.post(
            "/api/v1/auth/login",
            json={"identifier": f"scope-admin-{suffix}", "password": admin_password},
        ).status_code
        == 200
    )
    users = admin.get("/api/v1/admin/users?limit=200").json()
    priorities = {"pending": 0, "enabled": 1, "disabled": 2, "rejected": 3}
    assert [priorities[item["status"]] for item in users] == sorted(
        priorities[item["status"]] for item in users
    )

    assert (
        admin.post(
            "/api/v1/admin/projects", json={"code": f"P-{suffix}", "name": "Pipeline A"}
        ).status_code
        == 403
    )
    project_response = admin.post(
        "/api/v1/admin/projects",
        json={"code": f"P-{suffix}", "name": "Pipeline A"},
        headers=ORIGIN,
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    assert (
        admin.put(
            f"/api/v1/admin/users/{normal_user_id}/projects/{project_id}", headers=ORIGIN
        ).status_code
        == 204
    )

    user = TestClient(app)
    assert (
        user.post(
            "/api/v1/auth/login",
            json={"identifier": f"scope-user-{suffix}", "password": user_password},
        ).status_code
        == 200
    )
    projects = user.get("/api/v1/projects").json()
    assert [item["id"] for item in projects] == [project_id]
    assert admin.get("/api/v1/admin/audit-events").status_code == 200

    disabled = admin.patch(
        f"/api/v1/admin/users/{admin_user.id}/status",
        json={"status": "disabled"},
        headers=ORIGIN,
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
