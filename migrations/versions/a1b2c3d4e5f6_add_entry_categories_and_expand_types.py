"""add entry categories and expand types

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-04-13 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "account_payable",
        sa.Column("category_code", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "cash_outflow",
        sa.Column("category_code", sa.String(length=40), nullable=True),
    )

    op.execute(
        """
        UPDATE account_payable
        SET payable_type = CASE
            WHEN payable_type = 'merchandise' THEN 'merchandise'
            ELSE 'operational_expense'
        END
        """
    )
    op.execute(
        """
        UPDATE cash_outflow
        SET outflow_type = CASE
            WHEN outflow_type = 'merchandise' THEN 'merchandise'
            ELSE 'operational_expense'
        END
        """
    )

    op.execute(
        """
        UPDATE account_payable
        SET category_code = CASE
            WHEN payable_type = 'merchandise' THEN 'fornecedor'
            ELSE 'outros'
        END
        WHERE category_code IS NULL
        """
    )
    op.execute(
        """
        UPDATE cash_outflow
        SET category_code = CASE
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('aluguel') THEN 'aluguel'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('agua', 'água') THEN 'agua'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('luz') THEN 'luz'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('folha', 'folha de pagamento') THEN 'folha'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('pro labore', 'pro-labore') THEN 'pro_labore'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('retirada pessoal') THEN 'retirada_pessoal'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('manutencao', 'manutenção') THEN 'manutencao'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('imposto', 'impostos') THEN 'imposto'
            WHEN LOWER(TRIM(COALESCE(category, ''))) IN ('fornecedor') THEN 'fornecedor'
            WHEN outflow_type = 'merchandise' THEN 'fornecedor'
            ELSE 'outros'
        END
        WHERE category_code IS NULL
        """
    )

    op.alter_column("account_payable", "category_code", nullable=False)
    op.alter_column("cash_outflow", "category_code", nullable=False)


def downgrade():
    op.execute(
        """
        UPDATE account_payable
        SET payable_type = CASE
            WHEN payable_type = 'merchandise' THEN 'merchandise'
            ELSE 'operational'
        END
        """
    )
    op.execute(
        """
        UPDATE cash_outflow
        SET outflow_type = CASE
            WHEN outflow_type = 'merchandise' THEN 'merchandise'
            ELSE 'operational'
        END
        """
    )
    op.drop_column("cash_outflow", "category_code")
    op.drop_column("account_payable", "category_code")
