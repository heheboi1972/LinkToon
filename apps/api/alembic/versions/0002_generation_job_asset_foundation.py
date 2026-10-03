"""Generation job state machine and generated asset metadata.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

NEW_STATUS_CHECK = (
    "status IN ('queued','running','provider_pending','saving','succeeded','failed','canceled')"
)
OLD_STATUS_CHECK = (
    "status IN ('queued','planning','submitted','processing','postprocessing',"
    "'completed','failed','cancelled')"
)


def _add_job_columns(batch_op: Any, *, replace_status_check: bool) -> None:
    if replace_status_check:
        batch_op.drop_constraint("ck_job_status", type_="check")
    batch_op.add_column(
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
    )
    batch_op.add_column(
        sa.Column("provider_output", JSONType, server_default=sa.text("'{}'"), nullable=False)
    )
    batch_op.add_column(
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    batch_op.add_column(sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    batch_op.add_column(sa.Column("idempotency_key", sa.String(length=200), nullable=True))
    batch_op.add_column(sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    batch_op.add_column(sa.Column("lease_owner", sa.String(length=100), nullable=True))
    batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    batch_op.create_check_constraint("ck_job_status", NEW_STATUS_CHECK)
    batch_op.create_check_constraint("ck_job_retry_count", "retry_count >= 0")
    batch_op.create_unique_constraint("uq_jobs_user_idempotency", ["user_id", "idempotency_key"])
    batch_op.create_index(
        batch_op.f("ix_generation_jobs_next_poll_at"), ["next_poll_at"], unique=False
    )
    batch_op.create_index(
        batch_op.f("ix_generation_jobs_lease_expires_at"), ["lease_expires_at"], unique=False
    )
    batch_op.create_index("ix_jobs_status_poll", ["status", "next_poll_at"], unique=False)


def _drop_job_columns(batch_op: Any, *, replace_status_check: bool) -> None:
    batch_op.drop_index("ix_jobs_status_poll")
    batch_op.drop_index(batch_op.f("ix_generation_jobs_lease_expires_at"))
    batch_op.drop_index(batch_op.f("ix_generation_jobs_next_poll_at"))
    batch_op.drop_constraint("uq_jobs_user_idempotency", type_="unique")
    batch_op.drop_constraint("ck_job_retry_count", type_="check")
    if replace_status_check:
        batch_op.drop_constraint("ck_job_status", type_="check")
    batch_op.create_check_constraint("ck_job_status", OLD_STATUS_CHECK)
    batch_op.drop_column("lease_expires_at")
    batch_op.drop_column("lease_owner")
    batch_op.drop_column("cancel_requested_at")
    batch_op.drop_column("idempotency_key")
    batch_op.drop_column("next_poll_at")
    batch_op.drop_column("retry_count")
    batch_op.drop_column("provider_output")
    batch_op.drop_column("updated_at")


def upgrade() -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    if sqlite:
        op.execute("PRAGMA foreign_keys = OFF")
        op.execute("PRAGMA ignore_check_constraints = ON")
    else:
        op.drop_constraint("ck_job_status", "generation_jobs", type_="check")

    op.execute(
        sa.text(
            """
            UPDATE generation_jobs
            SET status = CASE status
                WHEN 'planning' THEN 'running'
                WHEN 'submitted' THEN 'provider_pending'
                WHEN 'processing' THEN 'provider_pending'
                WHEN 'postprocessing' THEN 'saving'
                WHEN 'completed' THEN 'succeeded'
                WHEN 'cancelled' THEN 'canceled'
                ELSE status
            END
            """
        )
    )
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        _add_job_columns(batch_op, replace_status_check=sqlite)
    if sqlite:
        op.execute("PRAGMA ignore_check_constraints = OFF")

    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("storage_bucket", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=20),
                server_default=sa.text("'upload'"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("provider", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("provider_task_id", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("generation_job_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("prompt", sa.String(), nullable=True))
        batch_op.create_check_constraint("ck_asset_source", "source IN ('upload','generated')")
        batch_op.create_foreign_key(
            "fk_assets_generation_job",
            "generation_jobs",
            ["generation_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_assets_generation_job_id"), ["generation_job_id"], unique=False
        )
    if sqlite:
        op.execute("PRAGMA foreign_keys = ON")


def downgrade() -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    if sqlite:
        op.execute("PRAGMA foreign_keys = OFF")

    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assets_generation_job_id"))
        batch_op.drop_constraint("fk_assets_generation_job", type_="foreignkey")
        batch_op.drop_constraint("ck_asset_source", type_="check")
        batch_op.drop_column("prompt")
        batch_op.drop_column("generation_job_id")
        batch_op.drop_column("provider_task_id")
        batch_op.drop_column("provider")
        batch_op.drop_column("source")
        batch_op.drop_column("storage_bucket")

    if sqlite:
        op.execute("PRAGMA ignore_check_constraints = ON")
    else:
        op.drop_constraint("ck_job_status", "generation_jobs", type_="check")

    op.execute(
        sa.text(
            """
            UPDATE generation_jobs
            SET status = CASE status
                WHEN 'running' THEN 'planning'
                WHEN 'provider_pending' THEN 'processing'
                WHEN 'saving' THEN 'postprocessing'
                WHEN 'succeeded' THEN 'completed'
                WHEN 'canceled' THEN 'cancelled'
                ELSE status
            END
            """
        )
    )
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        _drop_job_columns(batch_op, replace_status_check=sqlite)
    if sqlite:
        op.execute("PRAGMA ignore_check_constraints = OFF")
        op.execute("PRAGMA foreign_keys = ON")
