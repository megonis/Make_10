"""baseline

Revision ID: 7457f30e8fd1
Revises: 
Create Date: 2026-03-16 21:06:49.245669

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7457f30e8fd1'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "fixed_expense",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("monthly_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "daily_sale",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["store.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_daily_sale_sale_date"), "daily_sale", ["sale_date"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_daily_sale_sale_date"), table_name="daily_sale")
    op.drop_table("daily_sale")
    op.drop_table("fixed_expense")
    op.drop_table("store")
