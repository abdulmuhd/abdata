"""add profit_kobo to vtu_transactions

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vtu_transactions", sa.Column("profit_kobo", sa.BigInteger(), server_default="0"))


def downgrade() -> None:
    op.drop_column("vtu_transactions", "profit_kobo")
