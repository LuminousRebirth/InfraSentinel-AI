from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infrasentinel.auth import hash_password
from infrasentinel.database import Base, SessionLocal, get_engine
from infrasentinel.errors import InfraError
from infrasentinel.models import User, UserRole, UserStatus
from infrasentinel.schemas import RegisterRequest, UserStatusUpdate
from infrasentinel.services import bootstrap_admin, register_user, update_user_status


def test_registration_and_bootstrap_lifecycle() -> None:
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal(bind=get_engine()) as db:
        admin, created = bootstrap_admin(
            db,
            email=f"admin-{suffix}@example.com",
            username=f"admin-{suffix}",
            password="correct horse battery staple",
            display_name="Test Administrator",
            locale="en",
        )
        same_admin, created_again = bootstrap_admin(
            db,
            email=admin.email,
            username=admin.username,
            password="a different password is ignored",
            display_name="Ignored",
            locale="zh-CN",
        )
        user = register_user(
            db,
            RegisterRequest(
                email=f"user-{suffix}@example.com",
                username=f"user-{suffix}",
                display_name="Normal User",
                password="correct horse battery staple",
                locale="zh-CN",
            ),
            source_ip="127.0.0.1",
            user_agent="pytest",
        )

        assert created is True
        assert created_again is False
        assert same_admin.id == admin.id
        assert admin.role == UserRole.ADMIN
        assert admin.status == UserStatus.ENABLED
        assert user.role == UserRole.USER
        assert user.status == UserStatus.PENDING


def test_last_enabled_admin_cannot_be_disabled() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            email="only-admin@example.com",
            username="only-admin",
            display_name="Only Administrator",
            password_hash=hash_password("correct horse battery staple"),
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
            locale="en",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        with pytest.raises(InfraError) as error:
            update_user_status(
                db,
                actor=admin,
                target=admin,
                payload=UserStatusUpdate(status="disabled"),
                source_ip="127.0.0.1",
                user_agent="pytest",
            )

        assert error.value.code == "admin.last_admin"
