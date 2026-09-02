"""Create alert intelligence tables."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260902_0004"
down_revision = "20260902_0003"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name_zh", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("merge_window_ms", sa.Integer(), nullable=False),
        sa.Column("iou_threshold", sa.Float(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("risk_level IN ('low','medium','high')", name="ck_alert_rules_level"),
        sa.CheckConstraint("min_confidence BETWEEN 0 AND 1", name="ck_alert_rules_confidence"),
        sa.CheckConstraint("merge_window_ms BETWEEN 0 AND 600000", name="ck_alert_rules_window"),
        sa.CheckConstraint("iou_threshold BETWEEN 0 AND 1", name="ck_alert_rules_iou"),
        sa.CheckConstraint("cooldown_seconds BETWEEN 0 AND 86400", name="ck_alert_rules_cooldown"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_code", "alert_rules", ["code"], unique=True)
    op.create_index("ix_alert_rules_class_name", "alert_rules", ["class_name"])
    op.create_index(
        "ix_alert_rules_match", "alert_rules", ["project_id", "class_name", "enabled", "priority"]
    )

    op.create_table(
        "detection_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("first_frame", sa.Integer(), nullable=False),
        sa.Column("last_frame", sa.Integer(), nullable=False),
        sa.Column("first_timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("last_timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("max_confidence", sa.Float(), nullable=False),
        sa.Column("representative_observation_id", sa.Uuid(), nullable=False),
        sa.Column("keyframe_media_id", sa.Uuid(), nullable=True),
        sa.Column("last_box_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_events_status"),
        sa.CheckConstraint("first_timestamp_ms >= 0", name="ck_events_first_time"),
        sa.CheckConstraint("last_timestamp_ms >= first_timestamp_ms", name="ck_events_last_time"),
        sa.CheckConstraint("observation_count > 0", name="ck_events_count"),
        sa.CheckConstraint("max_confidence BETWEEN 0 AND 1", name="ck_events_confidence"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["vision_models.id"]),
        sa.ForeignKeyConstraint(
            ["representative_observation_id"], ["detection_observations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["keyframe_media_id"], ["detection_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_fingerprint", "detection_events", ["fingerprint"], unique=True)
    op.create_index("ix_events_job_id", "detection_events", ["job_id"])
    op.create_index("ix_events_project_id", "detection_events", ["project_id"])
    op.create_index("ix_events_owner_id", "detection_events", ["owner_id"])
    op.create_index("ix_events_class_name", "detection_events", ["class_name"])
    op.create_index("ix_events_project_created", "detection_events", ["project_id", "created_at"])
    op.create_index(
        "ix_events_job_class_time",
        "detection_events",
        ["job_id", "class_name", "first_timestamp_ms"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("final_level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title_zh", sa.String(250), nullable=False),
        sa.Column("title_en", sa.String(250), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=True),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("final_level IN ('low','medium','high')", name="ck_alerts_level"),
        sa.CheckConstraint(
            "status IN ('pending_confirmation','assigned','processing',"
            "'resolved','false_positive')",
            name="ck_alerts_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_alerts_version"),
        sa.ForeignKeyConstraint(["event_id"], ["detection_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])
    op.create_index("ix_alerts_owner_id", "alerts", ["owner_id"])
    op.create_index("ix_alerts_final_level", "alerts", ["final_level"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index(
        "ix_alerts_project_status_created", "alerts", ["project_id", "status", "created_at"]
    )
    op.create_index("ix_alerts_assignee_status", "alerts", ["assignee_id", "status"])

    op.create_table(
        "alert_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column("after_state", JSONB, nullable=True),
        sa.Column("detail", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_actions_alert_id", "alert_actions", ["alert_id"])
    op.create_index("ix_alert_actions_alert_created", "alert_actions", ["alert_id", "created_at"])

    op.create_table(
        "alert_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("uploader_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size > 0", name="ck_alert_attachment_size"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_alert_attachments_alert_id", "alert_attachments", ["alert_id"])

    op.create_table(
        "llm_provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('qwen','deepseek','glm')", name="ck_llm_provider_kind"),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 300", name="ck_llm_provider_timeout"),
        sa.CheckConstraint("max_retries BETWEEN 0 AND 5", name="ck_llm_provider_retries"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_provider_code", "llm_provider_configs", ["code"], unique=True)

    op.create_table(
        "llm_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_config_id", sa.Uuid(), nullable=False),
        sa.Column("scope_key", sa.String(50), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_hint", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["llm_provider_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_config_id", "scope_key"),
    )
    op.create_index("ix_llm_credentials_provider", "llm_credentials", ["provider_config_id"])

    op.create_table(
        "llm_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("provider_config_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("prefer_personal", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", JSONB, nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.String(1000), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(job_id IS NOT NULL AND event_id IS NULL) OR "
            "(job_id IS NULL AND event_id IS NOT NULL)",
            name="ck_llm_analysis_target",
        ),
        sa.CheckConstraint(
            "status IN ('waiting_configuration','queued','running',"
            "'succeeded','failed','cancelled')",
            name="ck_llm_analysis_status",
        ),
        sa.CheckConstraint("attempt >= 1 AND max_attempts >= attempt", name="ck_llm_attempts"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["detection_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["llm_provider_configs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_llm_analysis_owner", "llm_analyses", ["owner_id"])
    op.create_index("ix_llm_analysis_status", "llm_analyses", ["status"])
    op.create_index("ix_llm_analysis_queue", "llm_analyses", ["status", "requested_at"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("provider_config_id", sa.Uuid(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_bytes", sa.BigInteger(), nullable=False),
        sa.Column("response_bytes", sa.BigInteger(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["llm_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_config_id"], ["llm_provider_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_calls_analysis", "llm_calls", ["analysis_id"])


def downgrade() -> None:
    for table in (
        "llm_calls",
        "llm_analyses",
        "llm_credentials",
        "llm_provider_configs",
        "alert_attachments",
        "alert_actions",
        "alerts",
        "detection_events",
        "alert_rules",
    ):
        op.drop_table(table)
