"""Add immutable publication snapshots and stable public slugs.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "publications",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('private','unlisted','public')", name="ck_publication_visibility"
        ),
        sa.CheckConstraint(
            "status IN ('published','unpublished')", name="ck_publication_status"
        ),
        sa.CheckConstraint("current_version > 0", name="ck_publication_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", name="uq_publication_episode"),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("publications") as batch_op:
        batch_op.create_index("ix_publications_owner_id", ["owner_id"], unique=False)
        batch_op.create_index("ix_publications_project_id", ["project_id"], unique=False)
        batch_op.create_index(
            "ix_publications_project_status", ["project_id", "status"], unique=False
        )

    op.create_table(
        "publication_snapshots",
        sa.Column("publication_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("episode_title", sa.String(length=120), nullable=False),
        sa.Column("episode_description", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publication_id", "version", name="uq_publication_snapshot"),
    )
    with op.batch_alter_table("publication_snapshots") as batch_op:
        batch_op.create_index("ix_publication_snapshots_publication_id", ["publication_id"])

    op.create_table(
        "publication_scenes",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_scene_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("narration", sa.String(), nullable=False),
        sa.Column("dialogue", json_type, nullable=False),
        sa.Column("image_asset_id", sa.Uuid(), nullable=True),
        sa.Column("video_asset_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["publication_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["video_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "position", name="uq_publication_scene_position"),
        sa.CheckConstraint("position >= 0", name="ck_publication_scene_position"),
    )
    with op.batch_alter_table("publication_scenes") as batch_op:
        batch_op.create_index("ix_publication_scenes_snapshot_id", ["snapshot_id"])
        batch_op.create_index("ix_publication_scenes_image_asset_id", ["image_asset_id"])
        batch_op.create_index("ix_publication_scenes_video_asset_id", ["video_asset_id"])


def downgrade() -> None:
    op.drop_table("publication_scenes")
    op.drop_table("publication_snapshots")
    op.drop_table("publications")
