"""remove unused push fields

Revision ID: d4f9a2c7e613
Revises: f2d8c6a4e901
Create Date: 2026-07-13 09:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4f9a2c7e613"
down_revision = "f2d8c6a4e901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("push_token")
        batch_op.drop_column("platform")


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("platform", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("push_token", sa.String(length=500), nullable=True))
