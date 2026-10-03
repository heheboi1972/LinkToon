"""Add the generated motion video pointer to scenes.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scenes") as batch_op:
        batch_op.add_column(sa.Column("video_asset_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_scenes_video_asset", "assets", ["video_asset_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index("ix_scenes_video_asset_id", ["video_asset_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch_op:
        batch_op.drop_index("ix_scenes_video_asset_id")
        batch_op.drop_constraint("fk_scenes_video_asset", type_="foreignkey")
        batch_op.drop_column("video_asset_id")
