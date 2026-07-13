"""remove user roles

Revision ID: b1a6d3e8c204
Revises: 9c4b2f7a1d63
Create Date: 2026-07-13 07:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b1a6d3e8c204"
down_revision = "9c4b2f7a1d63"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_role")
        batch_op.drop_column("role")


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sa.String(length=20),
                nullable=False,
                server_default="USER",
            )
        )
        batch_op.create_index("ix_users_role", ["role"], unique=False)
