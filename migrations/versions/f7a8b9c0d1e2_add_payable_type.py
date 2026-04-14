"""add payable type

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-04-13 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "account_payable",
        sa.Column("payable_type", sa.String(length=20), nullable=True),
    )
    op.execute("UPDATE account_payable SET payable_type = 'operational' WHERE payable_type IS NULL")
    op.alter_column("account_payable", "payable_type", nullable=False)


def downgrade():
    op.drop_column("account_payable", "payable_type")
