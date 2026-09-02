from __future__ import annotations

import argparse
import json

from .config import get_settings
from .database import SessionLocal, get_engine
from .errors import InfraError
from .health import readiness
from .intelligence_service import backfill_intelligence, seed_default_rules
from .services import bootstrap_admin
from .vision_models import sync_vision_models


def main() -> int:
    parser = argparse.ArgumentParser(prog="infrasentinel")
    parser.add_argument(
        "command",
        choices=[
            "health",
            "init-admin",
            "sync-vision-models",
            "seed-alert-rules",
            "backfill-intelligence",
        ],
    )
    args = parser.parse_args()

    if args.command == "health":
        result = readiness()
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        return 0 if result.status == "ready" else 1
    if args.command == "init-admin":
        settings = get_settings()
        email = settings.infrasentinel_bootstrap_admin_email
        username = settings.infrasentinel_bootstrap_admin_username
        password = settings.infrasentinel_bootstrap_admin_password
        if not email or not username or password is None:
            parser.error("bootstrap administrator environment variables are required")
        try:
            with SessionLocal(bind=get_engine()) as db:
                user, created = bootstrap_admin(
                    db,
                    email=email,
                    username=username,
                    password=password.get_secret_value(),
                    display_name=settings.infrasentinel_bootstrap_admin_display_name,
                    locale=settings.infrasentinel_bootstrap_admin_locale,
                )
        except InfraError as exc:
            parser.error(exc.code)
        state = "created" if created else "already exists"
        print(f"Administrator {user.email} {state}.")
        return 0
    if args.command == "sync-vision-models":
        with SessionLocal(bind=get_engine()) as db:
            models = sync_vision_models(db, get_settings())
        summary = [
            {
                "code": model.code,
                "scene": model.scene,
                "availability": model.availability,
                "version": model.version_label,
                "engine_configured": bool(model.engine_path),
            }
            for model in models
        ]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.command == "seed-alert-rules":
        with SessionLocal(bind=get_engine()) as db:
            rules = seed_default_rules(db)
        print(json.dumps({"rules": len(rules)}, ensure_ascii=False))
        return 0
    if args.command == "backfill-intelligence":
        with SessionLocal(bind=get_engine()) as db:
            jobs = backfill_intelligence(db)
        print(json.dumps({"jobs": jobs}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
