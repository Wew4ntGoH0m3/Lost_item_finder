"""remove site codes

Revision ID: e8a1c5b9d204
Revises: d4f9a2c7e613
Create Date: 2026-07-13 09:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e8a1c5b9d204"
down_revision = "d4f9a2c7e613"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_site_code")
        batch_op.drop_column("site_code")

    with op.batch_alter_table("lost_posts") as batch_op:
        batch_op.drop_index("ix_lost_post_match_candidates")
        batch_op.drop_index("ix_lost_posts_site_code")
        batch_op.drop_column("site_code")
        batch_op.create_index(
            "ix_lost_post_match_candidates",
            ["status", "category", "lost_at"],
            unique=False,
        )

    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.drop_index("ix_found_post_match_candidates")
        batch_op.drop_index("ix_found_posts_site_code")
        batch_op.drop_column("site_code")
        batch_op.create_index(
            "ix_found_post_match_candidates",
            ["status", "category", "found_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "site_code",
                sa.String(length=50),
                nullable=False,
                server_default="SCHOOL_001",
            )
        )
        batch_op.create_index("ix_users_site_code", ["site_code"], unique=False)

    with op.batch_alter_table("lost_posts") as batch_op:
        batch_op.drop_index("ix_lost_post_match_candidates")
        batch_op.add_column(
            sa.Column(
                "site_code",
                sa.String(length=50),
                nullable=False,
                server_default="SCHOOL_001",
            )
        )
        batch_op.create_index("ix_lost_posts_site_code", ["site_code"], unique=False)
        batch_op.create_index(
            "ix_lost_post_match_candidates",
            ["site_code", "status", "category", "lost_at"],
            unique=False,
        )

    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.drop_index("ix_found_post_match_candidates")
        batch_op.add_column(
            sa.Column(
                "site_code",
                sa.String(length=50),
                nullable=False,
                server_default="SCHOOL_001",
            )
        )
        batch_op.create_index("ix_found_posts_site_code", ["site_code"], unique=False)
        batch_op.create_index(
            "ix_found_post_match_candidates",
            ["site_code", "status", "category", "found_at"],
            unique=False,
        )
