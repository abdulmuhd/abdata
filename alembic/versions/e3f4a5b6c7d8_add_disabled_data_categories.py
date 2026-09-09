"""Add disabled_data_categories table

Revision ID: e3f4a5b6c7d8
Revises: c1d2e3f4a5b6
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "e3f4a5b6c7d8"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "disabled_data_categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("network_code", sa.String(40), nullable=False, index=True),
        sa.Column("category", sa.String(40), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("network_code", "category", name="uq_network_category"),
    )


def downgrade() -> None:
    op.drop_table("disabled_data_categories")
