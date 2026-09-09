"""add buying_price_kobo and selling_price_kobo to data_plans

Revision ID: b4e5f6a7c8d9
Revises: a3f1c8d92b47
Create Date: 2026-08-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4e5f6a7c8d9'
down_revision: Union[str, None] = 'a3f1c8d92b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('data_plans', sa.Column('buying_price_kobo', sa.BigInteger(), nullable=True))
    op.add_column('data_plans', sa.Column('selling_price_kobo', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('data_plans', 'selling_price_kobo')
    op.drop_column('data_plans', 'buying_price_kobo')
