"""Create platform metadata table."""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_metadata_key", "platform_metadata", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_platform_metadata_key", table_name="platform_metadata")
    op.drop_table("platform_metadata")
