"""V1 relational foundation

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Frozen migration: JSON uses JSONB on PostgreSQL and JSON on SQLite.
    op.create_table(
        "profiles",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "projects",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=False),
        sa.Column("orientation", sa.String(length=20), nullable=False),
        sa.Column("creation_mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("thumbnail_asset_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "creation_mode IN ('manual','assisted','ai_first')", name="ck_creation_mode"
        ),
        sa.CheckConstraint(
            "orientation IN ('vertical','horizontal')", name="ck_project_orientation"
        ),
        sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_project_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["thumbnail_asset_id"],
            ["assets.id"],
            name="fk_projects_thumbnail",
            ondelete="SET NULL",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index("ix_projects_owner_updated", ["owner_id", "updated_at"], unique=False)

    op.create_table(
        "assets",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("storage_provider", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("public_url", sa.String(), nullable=True),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("upload_status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "asset_type IN ('image','video','audio','mask','thumbnail','reference','export')",
            name="ck_asset_type",
        ),
        sa.CheckConstraint(
            "upload_status IN ('pending','uploaded','ready')", name="ck_asset_upload"
        ),
        sa.CheckConstraint("file_size > 0", name="ck_asset_size"),
        sa.ForeignKeyConstraint(["owner_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_assets_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_assets_project_id"), ["project_id"], unique=False)

    op.create_table(
        "episodes",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','public','unlisted','private')", name="ck_episode_status"
        ),
        sa.CheckConstraint("number > 0", name="ck_episode_number"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "number", name="uq_episode_number"),
    )
    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_episodes_project_id"), ["project_id"], unique=False)

    op.create_table(
        "generation_jobs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_model", sa.String(length=200), nullable=True),
        sa.Column("provider_task_id", sa.String(length=200), nullable=True),
        sa.Column(
            "input",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("cost_actual", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','planning','submitted','processing','postprocessing',"
            "'completed','failed','cancelled')",
            name="ck_job_status",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_job_progress"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_generation_jobs_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_generation_jobs_provider_task_id"), ["provider_task_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_generation_jobs_user_id"), ["user_id"], unique=False)
        batch_op.create_index("ix_jobs_user_created", ["user_id", "created_at"], unique=False)

    op.create_table(
        "project_bibles",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "story_bible",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "world_bible",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "visual_bible",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "prompt_rules",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "negative_rules",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "characters",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("appearance", sa.String(), nullable=False),
        sa.Column("personality", sa.String(), nullable=False),
        sa.Column("clothing", sa.String(), nullable=False),
        sa.Column("prompt_token", sa.String(length=100), nullable=False),
        sa.Column("primary_asset_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["primary_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_characters_project_id"), ["project_id"], unique=False)

    op.create_table(
        "publish_versions",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','public','unlisted','private')", name="ck_publish_status"
        ),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "version", name="uq_publish_version"),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("publish_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_publish_versions_episode_id"), ["episode_id"], unique=False
        )

    op.create_table(
        "scenes",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column(
            "script",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("scenes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_scenes_episode_id"), ["episode_id"], unique=False)

    op.create_table(
        "character_references",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("reference_type", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reference_type IN ('face','upper_body','full_body','pose','expression','outfit')",
            name="ck_reference_type",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("character_references", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_character_references_character_id"), ["character_id"], unique=False
        )

    op.create_table(
        "panels",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("dialogue", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("image_asset_id", sa.Uuid(), nullable=True),
        sa.Column(
            "script",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('empty','static','generating','animated')", name="ck_panel_status"
        ),
        sa.CheckConstraint("position >= 0", name="ck_panel_position"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "position", name="uq_panel_position"),
    )
    with op.batch_alter_table("panels", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_panels_episode_id"), ["episode_id"], unique=False)

    op.create_table(
        "animations",
        sa.Column("panel_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("webm_asset_id", sa.Uuid(), nullable=True),
        sa.Column("mp4_asset_id", sa.Uuid(), nullable=True),
        sa.Column("poster_asset_id", sa.Uuid(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mp4_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["poster_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["webm_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("animations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_animations_panel_id"), ["panel_id"], unique=False)

    op.create_table(
        "motion_layers",
        sa.Column("panel_id", sa.Uuid(), nullable=False),
        sa.Column("layer_type", sa.String(length=30), nullable=False),
        sa.Column("mask_asset_id", sa.Uuid(), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("z_index", sa.Integer(), nullable=False),
        sa.Column(
            "motion_config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mask_asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("motion_layers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_motion_layers_panel_id"), ["panel_id"], unique=False)

    op.create_table(
        "motion_plans",
        sa.Column("panel_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column(
            "analysis",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "plan",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('exact','partial_generate','full_generate','first_last')",
            name="ck_motion_mode",
        ),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("panel_id", "version", name="uq_motion_plan_version"),
    )
    with op.batch_alter_table("motion_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_motion_plans_panel_id"), ["panel_id"], unique=False)

    # The cover introduces a cycle: projects -> assets -> projects.
    # PostgreSQL needs the deferred FK after both tables exist; SQLite emits it inline.
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_projects_thumbnail",
            "projects",
            "assets",
            ["thumbnail_asset_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_projects_thumbnail", "projects", type_="foreignkey")
    with op.batch_alter_table("motion_plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_motion_plans_panel_id"))

    op.drop_table("motion_plans")
    with op.batch_alter_table("motion_layers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_motion_layers_panel_id"))

    op.drop_table("motion_layers")
    with op.batch_alter_table("animations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_animations_panel_id"))

    op.drop_table("animations")
    with op.batch_alter_table("panels", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_panels_episode_id"))

    op.drop_table("panels")
    with op.batch_alter_table("character_references", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_character_references_character_id"))

    op.drop_table("character_references")
    with op.batch_alter_table("scenes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenes_episode_id"))

    op.drop_table("scenes")
    with op.batch_alter_table("publish_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_publish_versions_episode_id"))

    op.drop_table("publish_versions")
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_characters_project_id"))

    op.drop_table("characters")
    op.drop_table("project_bibles")
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_jobs_user_created")
        batch_op.drop_index(batch_op.f("ix_generation_jobs_user_id"))
        batch_op.drop_index(batch_op.f("ix_generation_jobs_provider_task_id"))
        batch_op.drop_index(batch_op.f("ix_generation_jobs_project_id"))

    op.drop_table("generation_jobs")
    with op.batch_alter_table("episodes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_episodes_project_id"))

    op.drop_table("episodes")
    with op.batch_alter_table("assets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_assets_project_id"))
        batch_op.drop_index(batch_op.f("ix_assets_owner_id"))

    op.drop_table("assets")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index("ix_projects_owner_updated")
        batch_op.drop_index(batch_op.f("ix_projects_owner_id"))

    op.drop_table("projects")
    op.drop_table("profiles")
