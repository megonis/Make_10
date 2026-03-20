"""add cash outflows

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-03-20 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cash_outflow",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("outflow_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_outflow_outflow_date"), "cash_outflow", ["outflow_date"], unique=False)

    op.create_table(
        "cash_outflow_stores",
        sa.Column("cash_outflow_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cash_outflow_id"], ["cash_outflow.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("cash_outflow_id", "store_id"),
    )


def downgrade():
    op.drop_table("cash_outflow_stores")
    op.drop_index(op.f("ix_cash_outflow_outflow_date"), table_name="cash_outflow")
    op.drop_table("cash_outflow")
