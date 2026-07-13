"""add socket chat

Revision ID: 9c4b2f7a1d63
Revises: 7e2c1f4a9b10
Create Date: 2026-07-13 06:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "9c4b2f7a1d63"
down_revision = "7e2c1f4a9b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_rooms_match_id", "chat_rooms", ["match_id"], unique=True)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(length=1000), nullable=False),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "sender_id",
            "client_message_id",
            name="uq_chat_message_client_id",
        ),
    )
    op.create_index(
        "ix_chat_messages_created_at", "chat_messages", ["created_at"], unique=False
    )
    op.create_index("ix_chat_messages_room_id", "chat_messages", ["room_id"], unique=False)
    op.create_index(
        "ix_chat_messages_room_id_id", "chat_messages", ["room_id", "id"], unique=False
    )
    op.create_index(
        "ix_chat_messages_sender_id", "chat_messages", ["sender_id"], unique=False
    )

    op.create_table(
        "chat_room_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_read_message_id", sa.Integer(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_chat_room_member"),
    )
    op.create_index(
        "ix_chat_room_members_last_read_message_id",
        "chat_room_members",
        ["last_read_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_room_members_last_read_at",
        "chat_room_members",
        ["last_read_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_room_members_room_id", "chat_room_members", ["room_id"], unique=False
    )
    op.create_index(
        "ix_chat_room_members_user_id", "chat_room_members", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index("ix_chat_room_members_user_id", table_name="chat_room_members")
    op.drop_index("ix_chat_room_members_room_id", table_name="chat_room_members")
    op.drop_index("ix_chat_room_members_last_read_at", table_name="chat_room_members")
    op.drop_index(
        "ix_chat_room_members_last_read_message_id", table_name="chat_room_members"
    )
    op.drop_table("chat_room_members")

    op.drop_index("ix_chat_messages_sender_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_id_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_rooms_match_id", table_name="chat_rooms")
    op.drop_table("chat_rooms")
