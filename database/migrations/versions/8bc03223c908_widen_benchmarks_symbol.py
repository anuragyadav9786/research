"""widen benchmarks.symbol to match name

Revision ID: 8bc03223c908
Revises: 4f8db1ffc122
Create Date: 2026-10-21 12:30:00.000000

Real production bug: benchmark_catalogue_sync.py crashed inserting a real
AMC-disclosed benchmark whose name is a long custom blended-index
description ("35% BSE Oil & Gas Index +30% BSE Metal Index + 35% MSCI
World Energy 30% Buffer 10/40 Net Total Return", 100+ chars) into
`symbol`, which was capped at VARCHAR(100) while `name` is VARCHAR(255).
Widens `symbol` to match -- this is real, legitimate disclosed data, not
something to truncate or drop.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8bc03223c908'
down_revision: Union[str, Sequence[str], None] = '4f8db1ffc122'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('benchmarks', 'symbol', type_=sa.String(length=255))


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('benchmarks', 'symbol', type_=sa.String(length=100))
