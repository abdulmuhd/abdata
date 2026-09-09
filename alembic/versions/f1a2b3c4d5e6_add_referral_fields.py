"""add referral fields to users

Revision ID: f1a2b3c4d5e6
Revises: a3f1c8d92b47
Create Date: 2026-09-03
"""

import random
import string

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def _generate_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String(10), nullable=True, index=True))
    op.add_column("users", sa.Column("referred_by", sa.Integer(), nullable=True, index=True))

    # Backfill unique referral codes for existing users
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM users ORDER BY id")).fetchall()
    used = set()
    for (uid,) in rows:
        while True:
            code = _generate_code()
            if code not in used:
                used.add(code)
                conn.execute(sa.text("UPDATE users SET referral_code = :code WHERE id = :id"), {"code": code, "id": uid})
                break


def downgrade() -> None:
    op.drop_column("users", "referred_by")
    op.drop_column("users", "referral_code")
