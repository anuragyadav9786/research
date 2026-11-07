"""widen weight_pct upper bound for rounding slop

Revision ID: 2067640c39ae
Revises: 20d1a61d1425
Create Date: 2026-11-07 13:00:00.000000

A real AMC disclosure's reported "% to AUM" figures are independently
rounded per row and don't always sum to exactly 100%. For a liquid/
overnight fund with one dominant holding, that rounding can push the
single largest holding's own reported weight slightly over 100% (seen
in the real September 2026 ABSL disclosure: one holding at 100.202%).
The constraint's upper bound is widened from 100 to 105 to allow for
this real rounding slop while still catching genuine data errors.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2067640c39ae'
down_revision: Union[str, Sequence[str], None] = '20d1a61d1425'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_weight_pct_range', 'portfolio_holdings', type_='check')
    op.create_check_constraint(
        'ck_weight_pct_range', 'portfolio_holdings', 'weight_pct >= -100 AND weight_pct <= 105'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_weight_pct_range', 'portfolio_holdings', type_='check')
    op.create_check_constraint(
        'ck_weight_pct_range', 'portfolio_holdings', 'weight_pct >= -100 AND weight_pct <= 100'
    )
