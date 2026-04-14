"""adjust entry categories

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 00:40:00.000000

"""
from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE account_payable
        SET category_code = CASE
            WHEN category_code IN ('folha', 'pro_labore') THEN 'funcionarios'
            WHEN category_code = 'agua' THEN 'outros'
            ELSE category_code
        END
        """
    )
    op.execute(
        """
        UPDATE cash_outflow
        SET category_code = CASE
            WHEN category_code IN ('folha', 'pro_labore') THEN 'funcionarios'
            WHEN category_code = 'agua' THEN 'outros'
            ELSE category_code
        END
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE account_payable
        SET category_code = CASE
            WHEN category_code = 'funcionarios' THEN 'folha'
            WHEN category_code = 'outros' THEN 'agua'
            ELSE category_code
        END
        WHERE category_code IN ('funcionarios', 'outros')
        """
    )
    op.execute(
        """
        UPDATE cash_outflow
        SET category_code = CASE
            WHEN category_code = 'funcionarios' THEN 'folha'
            WHEN category_code = 'outros' THEN 'agua'
            ELSE category_code
        END
        WHERE category_code IN ('funcionarios', 'outros')
        """
    )
