"""Add structured Character Bible and canonical reference Asset linkage.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("character_bible", json_type, nullable=True))
        batch_op.add_column(sa.Column("appearance_lock", json_type, nullable=True))
        batch_op.add_column(sa.Column("style_lock", json_type, nullable=True))
        batch_op.add_column(sa.Column("reference_asset_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("character_revision", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("reference_generated_from_revision", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("reference_stale", sa.Boolean(), nullable=True))
        batch_op.create_foreign_key(
            "fk_characters_reference_asset",
            "assets",
            ["reference_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_characters_reference_asset_id", ["reference_asset_id"], unique=False
        )

    # Defaults are applied explicitly so this migration is safe on existing rows
    # and works consistently on SQLite and PostgreSQL.
    op.execute(
        sa.text("UPDATE characters SET character_bible = '{}' WHERE character_bible IS NULL")
    )
    op.execute(
        sa.text("UPDATE characters SET appearance_lock = '{}' WHERE appearance_lock IS NULL")
    )
    op.execute(sa.text("UPDATE characters SET style_lock = '{}' WHERE style_lock IS NULL"))
    op.execute(
        sa.text("UPDATE characters SET character_revision = 1 WHERE character_revision IS NULL")
    )
    op.execute(
        sa.text("UPDATE characters SET reference_stale = false WHERE reference_stale IS NULL")
    )
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.alter_column("character_bible", nullable=False, server_default=sa.text("'{}'"))
        batch_op.alter_column("appearance_lock", nullable=False, server_default=sa.text("'{}'"))
        batch_op.alter_column("style_lock", nullable=False, server_default=sa.text("'{}'"))
        batch_op.alter_column("character_revision", nullable=False, server_default="1")
        batch_op.alter_column("reference_stale", nullable=False, server_default=sa.false())


def downgrade() -> None:
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_index("ix_characters_reference_asset_id")
        batch_op.drop_constraint("fk_characters_reference_asset", type_="foreignkey")
        batch_op.drop_column("reference_stale")
        batch_op.drop_column("reference_generated_from_revision")
        batch_op.drop_column("character_revision")
        batch_op.drop_column("reference_asset_id")
        batch_op.drop_column("style_lock")
        batch_op.drop_column("appearance_lock")
        batch_op.drop_column("character_bible")
