from infrasentinel.database import Base
from infrasentinel.models import UserRole, UserStatus


def test_identity_metadata_contains_approved_tables() -> None:
    assert {
        "users",
        "auth_sessions",
        "projects",
        "project_memberships",
        "audit_events",
    } <= set(Base.metadata.tables)
    assert UserRole.ADMIN.value == "admin"
    assert UserStatus.PENDING.value == "pending"
