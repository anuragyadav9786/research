"""fund period returns screener

Revision ID: 4f8db1ffc122
Revises: e8a0094e9db4
Create Date: 2026-10-20 14:19:05.120037

Adds fund_period_returns (see FundPeriodReturn's docstring in
app/models/timeseries.py): one row per (scheme_variant, period), fed by
data_pipeline/orchestration/period_return_rollup.py's daily job. No raw
NAV time series is stored to produce this — bounded in size regardless of
how long the platform runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4f8db1ffc122'
down_revision: Union[str, Sequence[str], None] = 'e8a0094e9db4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fund_period_returns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scheme_variant_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=10), nullable=False),
        sa.Column('return_pct', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('anchor_date', sa.Date(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("period in ('1m', '3m', '6m', '1y', '3y', '5y')", name='ck_fund_period_return_period'),
        sa.ForeignKeyConstraint(['scheme_variant_id'], ['scheme_variants.id'], ),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scheme_variant_id', 'period', name='uq_fund_period_return_identity'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fund_period_returns')
