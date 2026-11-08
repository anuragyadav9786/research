"""allow negative weight_pct for net payable holdings

Revision ID: 20d1a61d1425
Revises: 5def88399ca5
Create Date: 2026-11-07 12:00:00.000000

A real AMC disclosure's "Net Receivable / Payable" line can be a net
payable (a liability), reported as a negative % to AUM and a negative
market value -- confirmed real while ingesting the real September 2026
ABSL disclosure (51 of 82 real schemes carry a negative "Net Receivable
/ Payable" row, one as low as -8.311%). The original constraint assumed
every holding is non-negative, which was true of every seed/sample
holding but not of this real AMC data.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '20d1a61d1425'
down_revision: Union[str, Sequence[str], None] = '5def88399ca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_weight_pct_range', 'portfolio_holdings', type_='check')
    op.create_check_constraint(
        'ck_weight_pct_range', 'portfolio_holdings', 'weight_pct >= -100 AND weight_pct <= 100'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_weight_pct_range', 'portfolio_holdings', type_='check')
    op.create_check_constraint(
        'ck_weight_pct_range', 'portfolio_holdings', 'weight_pct >= 0 AND weight_pct <= 100'
    )
