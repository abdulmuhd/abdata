"""add exam_products table + new service types

Revision ID: a3f1c8d92b47
Revises: e5d7d94705ee
Create Date: 2026-08-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c8d92b47'
down_revision: Union[str, None] = 'e5d7d94705ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exam_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('body_code', sa.String(length=40), nullable=False),
        sa.Column('product_code', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('price_kobo', sa.BigInteger(), nullable=False),
        sa.Column('meta', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_exam_products_body_code'), 'exam_products', ['body_code'], unique=False)
    op.create_index(op.f('ix_exam_products_product_code'), 'exam_products', ['product_code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_exam_products_product_code'), table_name='exam_products')
    op.drop_index(op.f('ix_exam_products_body_code'), table_name='exam_products')
    op.drop_table('exam_products')
