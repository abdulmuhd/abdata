"""add bonus_kobo to wallets

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wallets", sa.Column("bonus_kobo", sa.BigInteger(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("wallets", "bonus_kobo")
