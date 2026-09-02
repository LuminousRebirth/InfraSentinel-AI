from pathlib import Path


def test_v13_migration_is_reversible_and_constrained() -> None:
    migration = Path("alembic/versions/20260902_0004_alert_intelligence.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "20260902_0003"' in migration
    assert "def downgrade()" in migration
    for table in (
        "alert_rules",
        "detection_events",
        "alerts",
        "alert_actions",
        "llm_provider_configs",
        "llm_credentials",
        "llm_analyses",
        "llm_calls",
    ):
        assert f'"{table}"' in migration
    assert "ck_alerts_status" in migration
    assert "ck_llm_analysis_target" in migration
