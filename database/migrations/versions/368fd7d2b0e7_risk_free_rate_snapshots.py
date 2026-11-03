"""risk free rate snapshots

Revision ID: 368fd7d2b0e7
Revises: 62269a9a0111
Create Date: 2026-11-03 10:58:04.680060

Adds risk_free_rate_snapshots -- replaces the hardcoded
Settings.risk_free_rate = 0.07 placeholder (docs/data-sources.md's open
decision #4) with a real, confirmed-live feed: FBIL's unauthenticated
T-Bill benchmark JSON endpoint (https://www.fbil.org.in/wasdm/tbill/fetch?authenticated=false),
whose "3 Months" tenor is the conventional market equivalent of the
"91-day T-bill rate" used throughout for Sharpe/Sortino. See
data_pipeline/sources/riskfree/fbil_client.py's module docstring for the
confirmed response shape and data_pipeline/orchestration/lazy_risk_free_rate.py
for the fetch-and-cache logic that reads/writes this table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '368fd7d2b0e7'
down_revision: Union[str, Sequence[str], None] = '62269a9a0111'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'risk_free_rate_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('rate_pct', sa.Numeric(6, 4), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('as_of_date'),
        sa.CheckConstraint('rate_pct > 0', name='ck_risk_free_rate_positive'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('risk_free_rate_snapshots')
