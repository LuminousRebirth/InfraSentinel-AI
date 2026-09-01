from __future__ import annotations

from sqlalchemy import select

from infrasentinel.database import SessionLocal, get_engine
from infrasentinel.models import AuditEvent
from infrasentinel.services import record_audit


def test_audit_writer_redacts_nested_secrets() -> None:
    with SessionLocal(bind=get_engine()) as db:
        event = record_audit(
            db,
            action="test.redaction",
            target_type="test",
            after_state={
                "password": "plain",
                "nested": {"access_token": "raw", "safe": "visible"},
            },
        )
        db.commit()
        stored = db.scalar(select(AuditEvent).where(AuditEvent.id == event.id))
        assert stored is not None
        assert stored.after_state == {
            "password": "[REDACTED]",
            "nested": {"access_token": "[REDACTED]", "safe": "visible"},
        }
