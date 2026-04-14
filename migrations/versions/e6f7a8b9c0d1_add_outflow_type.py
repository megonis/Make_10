"""add outflow type

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-04-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cash_outflow",
        sa.Column("outflow_type", sa.String(length=20), nullable=True),
    )
    op.execute("UPDATE cash_outflow SET outflow_type = 'operational' WHERE outflow_type IS NULL")
    op.alter_column("cash_outflow", "outflow_type", nullable=False)


def downgrade():
    op.drop_column("cash_outflow", "outflow_type")
