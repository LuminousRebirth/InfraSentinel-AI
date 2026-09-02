"""Create durable vision detection tables."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260902_0003"
down_revision = "20260901_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vision_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_zh", sa.String(length=100), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=False),
        sa.Column("scene", sa.String(length=16), nullable=False),
        sa.Column("pt_path", sa.String(length=2048), nullable=True),
        sa.Column("engine_path", sa.String(length=2048), nullable=True),
        sa.Column("asset_sha256", sa.String(length=64), nullable=True),
        sa.Column("classes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_size", sa.Integer(), nullable=False),
        sa.Column("preferred_backend", sa.String(length=16), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("unavailable_reason", sa.String(length=500), nullable=True),
        sa.Column("version_label", sa.String(length=100), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scene IN ('pipeline', 'ppe')", name="ck_vision_models_scene"),
        sa.CheckConstraint(
            "preferred_backend IN ('auto', 'trt', 'pt')",
            name="ck_vision_models_backend",
        ),
        sa.CheckConstraint(
            "availability IN ('available', 'unavailable')",
            name="ck_vision_models_availability",
        ),
        sa.CheckConstraint("input_size BETWEEN 320 AND 1280", name="ck_vision_models_input"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vision_models_code", "vision_models", ["code"], unique=True)
    op.create_index("ix_vision_models_scene", "vision_models", ["scene"])

    op.create_table(
        "detection_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("point_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("scene", sa.String(length=16), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("progress_detail", sa.String(length=500), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_of_id", sa.Uuid(), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.String(length=1000), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('image', 'video', 'obs')", name="ck_detection_jobs_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'cancelling', 'cancelled', 'succeeded', 'failed')",
            name="ck_detection_jobs_status",
        ),
        sa.CheckConstraint("scene IN ('pipeline', 'ppe')", name="ck_detection_jobs_scene"),
        sa.CheckConstraint("point_id = project_id", name="ck_detection_jobs_provisional_point"),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100", name="ck_detection_jobs_progress"
        ),
        sa.CheckConstraint(
            "attempt >= 1 AND max_attempts >= attempt", name="ck_detection_jobs_attempts"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["point_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["model_id"], ["vision_models.id"]),
        sa.ForeignKeyConstraint(["retry_of_id"], ["detection_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_jobs_kind", "detection_jobs", ["kind"])
    op.create_index("ix_detection_jobs_project_id", "detection_jobs", ["project_id"])
    op.create_index("ix_detection_jobs_owner_id", "detection_jobs", ["owner_id"])
    op.create_index("ix_detection_jobs_model_id", "detection_jobs", ["model_id"])
    op.create_index("ix_detection_jobs_queue", "detection_jobs", ["status", "queued_at"])
    op.create_index(
        "ix_detection_jobs_owner_created", "detection_jobs", ["owner_id", "created_at"]
    )
    op.create_index(
        "ix_detection_jobs_project_created", "detection_jobs", ["project_id", "created_at"]
    )

    op.create_table(
        "detection_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('original', 'annotated', 'keyframe')", name="ck_media_role"),
        sa.CheckConstraint("media_type IN ('image', 'video')", name="ck_media_type"),
        sa.CheckConstraint("byte_size >= 0", name="ck_media_size"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_detection_media_job_id", "detection_media", ["job_id"])
    op.create_index("ix_detection_media_job_role", "detection_media", ["job_id", "role"])

    op.create_table(
        "detection_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=True),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("class_name", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column("inference_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("frame_index >= 0 AND timestamp_ms >= 0", name="ck_observation_time"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_observation_confidence"),
        sa.CheckConstraint("x2 >= x1 AND y2 >= y1", name="ck_observation_box"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["detection_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_observations_job_id", "detection_observations", ["job_id"])
    op.create_index(
        "ix_detection_observations_class_name", "detection_observations", ["class_name"]
    )
    op.create_index(
        "ix_detection_observations_job_time",
        "detection_observations",
        ["job_id", "timestamp_ms"],
    )

    op.create_table(
        "detection_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("sample_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_frames", sa.Integer(), nullable=False),
        sa.Column("effective_fps", sa.Float(), nullable=False),
        sa.Column("inference_p50_ms", sa.Float(), nullable=False),
        sa.Column("gpu_percent", sa.Float(), nullable=True),
        sa.Column("gpu_memory_used_mb", sa.Integer(), nullable=True),
        sa.Column("gpu_memory_total_mb", sa.Integer(), nullable=True),
        sa.CheckConstraint("processed_frames >= 0", name="ck_metrics_frames"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detection_metrics_job_id", "detection_metrics", ["job_id"])
    op.create_index(
        "ix_detection_metrics_job_sample", "detection_metrics", ["job_id", "sample_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_detection_metrics_job_sample", table_name="detection_metrics")
    op.drop_index("ix_detection_metrics_job_id", table_name="detection_metrics")
    op.drop_table("detection_metrics")
    op.drop_index("ix_detection_observations_job_time", table_name="detection_observations")
    op.drop_index("ix_detection_observations_class_name", table_name="detection_observations")
    op.drop_index("ix_detection_observations_job_id", table_name="detection_observations")
    op.drop_table("detection_observations")
    op.drop_index("ix_detection_media_job_role", table_name="detection_media")
    op.drop_index("ix_detection_media_job_id", table_name="detection_media")
    op.drop_table("detection_media")
    op.drop_index("ix_detection_jobs_project_created", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_owner_created", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_queue", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_model_id", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_owner_id", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_project_id", table_name="detection_jobs")
    op.drop_index("ix_detection_jobs_kind", table_name="detection_jobs")
    op.drop_table("detection_jobs")
    op.drop_index("ix_vision_models_scene", table_name="vision_models")
    op.drop_index("ix_vision_models_code", table_name="vision_models")
    op.drop_table("vision_models")
