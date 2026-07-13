"""add found content generation metadata

Revision ID: f2d8c6a4e901
Revises: b1a6d3e8c204
Create Date: 2026-07-13 07:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f2d8c6a4e901"
down_revision = "b1a6d3e8c204"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_observations",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "content_generator",
                sa.String(length=100),
                nullable=False,
                server_default="legacy/manual-v1",
            )
        )
    op.execute("UPDATE found_posts SET source_observations = features")


def downgrade():
    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.drop_column("content_generator")
        batch_op.drop_column("source_observations")
