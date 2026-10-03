"""Link each Scene to its current generated image Asset.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scenes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("image_asset_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_scenes_image_asset",
            "assets",
            ["image_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_scenes_image_asset_id"), ["image_asset_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("scenes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenes_image_asset_id"))
        batch_op.drop_constraint("fk_scenes_image_asset", type_="foreignkey")
        batch_op.drop_column("image_asset_id")
