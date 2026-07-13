"""add category enum tags and candidate index

Revision ID: 7e2c1f4a9b10
Revises: 11dcefc5c1a0
Create Date: 2026-07-13 05:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "7e2c1f4a9b10"
down_revision = "11dcefc5c1a0"
branch_labels = None
depends_on = None

CATEGORIES = (
    "CARD",
    "WALLET",
    "EARPHONE",
    "BAG",
    "KEY",
    "ELECTRONICS",
    "CLOTHING",
    "UMBRELLA",
    "STATIONERY",
    "ETC",
)
CATEGORY_CHECK = "category IN ({})".format(
    ", ".join(f"'{category}'" for category in CATEGORIES)
)


def _normalize_categories(table_name: str):
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET category = CASE UPPER(category)
                WHEN 'CARD' THEN 'CARD'
                WHEN 'ID_CARD' THEN 'CARD'
                WHEN 'STUDENT_ID' THEN 'CARD'
                WHEN '카드' THEN 'CARD'
                WHEN '학생증' THEN 'CARD'
                WHEN '신분증' THEN 'CARD'
                WHEN 'WALLET' THEN 'WALLET'
                WHEN 'CARD_WALLET' THEN 'WALLET'
                WHEN '지갑' THEN 'WALLET'
                WHEN '카드지갑' THEN 'WALLET'
                WHEN 'EARPHONE' THEN 'EARPHONE'
                WHEN 'EARPHONE_CASE' THEN 'EARPHONE'
                WHEN 'AIRPODS' THEN 'EARPHONE'
                WHEN '이어폰' THEN 'EARPHONE'
                WHEN '에어팟' THEN 'EARPHONE'
                WHEN '이어폰케이스' THEN 'EARPHONE'
                WHEN 'BAG' THEN 'BAG'
                WHEN 'BACKPACK' THEN 'BAG'
                WHEN '가방' THEN 'BAG'
                WHEN '백팩' THEN 'BAG'
                WHEN 'KEY' THEN 'KEY'
                WHEN 'KEYRING' THEN 'KEY'
                WHEN '열쇠' THEN 'KEY'
                WHEN '키링' THEN 'KEY'
                WHEN 'ELECTRONICS' THEN 'ELECTRONICS'
                WHEN 'ELECTRONIC' THEN 'ELECTRONICS'
                WHEN 'PHONE' THEN 'ELECTRONICS'
                WHEN 'LAPTOP' THEN 'ELECTRONICS'
                WHEN '전자기기' THEN 'ELECTRONICS'
                WHEN 'CLOTHING' THEN 'CLOTHING'
                WHEN '옷' THEN 'CLOTHING'
                WHEN '의류' THEN 'CLOTHING'
                WHEN 'UMBRELLA' THEN 'UMBRELLA'
                WHEN '우산' THEN 'UMBRELLA'
                WHEN 'STATIONERY' THEN 'STATIONERY'
                WHEN '문구' THEN 'STATIONERY'
                WHEN '문구류' THEN 'STATIONERY'
                WHEN 'ETC' THEN 'ETC'
                ELSE 'ETC'
            END
            """
        )
    )


def upgrade():
    _normalize_categories("lost_posts")
    _normalize_categories("found_posts")

    with op.batch_alter_table("lost_posts") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=50),
            type_=sa.String(length=11),
            existing_nullable=False,
        )
        batch_op.create_check_constraint("ck_lost_posts_category_enum", CATEGORY_CHECK)
        batch_op.create_index(
            "ix_lost_post_match_candidates",
            ["site_code", "status", "category", "lost_at"],
            unique=False,
        )

    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=50),
            type_=sa.String(length=11),
            existing_nullable=False,
        )
        batch_op.create_check_constraint("ck_found_posts_category_enum", CATEGORY_CHECK)


def downgrade():
    with op.batch_alter_table("lost_posts") as batch_op:
        batch_op.drop_index("ix_lost_post_match_candidates")
        batch_op.drop_constraint("ck_lost_posts_category_enum", type_="check")
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=11),
            type_=sa.String(length=50),
            existing_nullable=False,
        )

    with op.batch_alter_table("found_posts") as batch_op:
        batch_op.drop_constraint("ck_found_posts_category_enum", type_="check")
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=11),
            type_=sa.String(length=50),
            existing_nullable=False,
        )
