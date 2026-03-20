"""add account payables

Revision ID: c1d2e3f4a5b6
Revises: 7457f30e8fd1
Create Date: 2026-03-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "7457f30e8fd1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_payable",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.Column("is_paid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_payable_due_date"), "account_payable", ["due_date"], unique=False)

    op.create_table(
        "account_payable_stores",
        sa.Column("account_payable_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["account_payable_id"], ["account_payable.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("account_payable_id", "store_id"),
    )


def downgrade():
    op.drop_table("account_payable_stores")
    op.drop_index(op.f("ix_account_payable_due_date"), table_name="account_payable")
    op.drop_table("account_payable")
