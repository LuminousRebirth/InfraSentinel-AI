from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from infrasentinel.database import get_engine, utc_now


@pytest.mark.integration
def test_identity_schema_and_audit_trigger() -> None:
    engine = get_engine()
    assert {
        "users",
        "auth_sessions",
        "projects",
        "project_memberships",
        "audit_events",
    } <= set(inspect(engine).get_table_names())

    event_id = uuid.uuid4()
    with engine.connect() as connection, connection.begin():
        connection.execute(
            text(
                """
                INSERT INTO audit_events
                    (id, action, target_type, result, created_at)
                VALUES
                    (:id, 'test.audit', 'test', 'success', :created_at)
                """
            ),
            {"id": event_id, "created_at": utc_now()},
        )
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("UPDATE audit_events SET action = 'changed' WHERE id = :id"),
                {"id": event_id},
            )
