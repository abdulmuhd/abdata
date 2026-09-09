"""add promo_codes table

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "g2h3i4j5k6l7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), unique=True, index=True, nullable=False),
        sa.Column("discount_percent", sa.Integer(), server_default="0"),
        sa.Column("discount_kobo", sa.Integer(), server_default="0"),
        sa.Column("max_uses", sa.Integer(), server_default="0"),
        sa.Column("used_count", sa.Integer(), server_default="0"),
        sa.Column("min_amount_kobo", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("promo_codes")
