"""add promo_price_kobo to data_plans

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_plans", sa.Column("promo_price_kobo", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("data_plans", "promo_price_kobo")
