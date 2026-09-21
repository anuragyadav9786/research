"""phase 17 benchmark data engine

Revision ID: e8a0094e9db4
Revises: 26787cf5af7a
Create Date: 2026-09-21 14:00:00.000000

Extends the existing benchmarks/benchmark_history tables (already the
"benchmarks"/"benchmark_prices" design the benchmark-engine spec asks
for — reused, not duplicated) with provider metadata, and adds
fund_benchmark_history for scheme-level benchmark assignments that can
change over time (mirrors the existing fund_manager_history table's
scheme_id + start_date/end_date shape).

Existing schemes.benchmark_id stays the authoritative CURRENT pointer —
untouched, every existing reader keeps working. The backfill step below
only ADDS a corresponding fund_benchmark_history row for schemes that
already have one, with start_date left NULL (the date that assignment
began is not known from any current source, and is never guessed).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8a0094e9db4'
down_revision: Union[str, Sequence[str], None] = '26787cf5af7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('benchmarks', sa.Column('provider', sa.String(length=50), nullable=True))
    op.add_column('benchmarks', sa.Column('symbol', sa.String(length=100), nullable=True))
    op.add_column('benchmarks', sa.Column('benchmark_type', sa.String(length=20), nullable=True))
    op.add_column(
        'benchmarks',
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
    )
    op.add_column(
        'benchmarks',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    )
    op.add_column('benchmarks', sa.Column('last_data_date', sa.Date(), nullable=True))
    op.add_column('benchmarks', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.add_column('benchmarks', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        'ck_benchmark_type', 'benchmarks', "benchmark_type in ('TRI', 'PRICE')"
    )

    op.add_column(
        'benchmark_history',
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_check_constraint('ck_benchmark_value_positive', 'benchmark_history', 'value > 0')

    op.create_table(
        'fund_benchmark_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scheme_id', sa.Integer(), nullable=False),
        sa.Column('benchmark_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['scheme_id'], ['schemes.id']),
        sa.ForeignKeyConstraint(['benchmark_id'], ['benchmarks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_fund_benchmark_history_scheme_id', 'fund_benchmark_history', ['scheme_id']
    )
    op.create_index(
        'uq_fund_benchmark_history_current_per_scheme',
        'fund_benchmark_history',
        ['scheme_id'],
        unique=True,
        postgresql_where=sa.text('end_date IS NULL'),
    )

    # Backfill: give every scheme that already has a benchmark_id a
    # corresponding "current" fund_benchmark_history row, so the new
    # historical-capable table starts consistent with the existing
    # pointer. start_date is left NULL — genuinely unknown, never invented.
    op.execute(
        """
        INSERT INTO fund_benchmark_history (scheme_id, benchmark_id, start_date, end_date, source)
        SELECT id, benchmark_id, NULL, NULL, 'scheme.benchmark_id (legacy pointer, migrated)'
        FROM schemes
        WHERE benchmark_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_fund_benchmark_history_current_per_scheme', table_name='fund_benchmark_history')
    op.drop_index('ix_fund_benchmark_history_scheme_id', table_name='fund_benchmark_history')
    op.drop_table('fund_benchmark_history')

    op.drop_constraint('ck_benchmark_value_positive', 'benchmark_history', type_='check')
    op.drop_column('benchmark_history', 'created_at')

    op.drop_constraint('ck_benchmark_type', 'benchmarks', type_='check')
    op.drop_column('benchmarks', 'updated_at')
    op.drop_column('benchmarks', 'created_at')
    op.drop_column('benchmarks', 'last_data_date')
    op.drop_column('benchmarks', 'is_active')
    op.drop_column('benchmarks', 'currency')
    op.drop_column('benchmarks', 'benchmark_type')
    op.drop_column('benchmarks', 'symbol')
    op.drop_column('benchmarks', 'provider')
