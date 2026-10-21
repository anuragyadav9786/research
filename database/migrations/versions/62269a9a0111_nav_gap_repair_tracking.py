"""nav gap repair tracking

Revision ID: 62269a9a0111
Revises: 8bc03223c908
Create Date: 2026-10-21 15:10:00.000000

Adds scheme_variants.nav_gap_repair_attempted_at -- a real production bug
(confirmed live) left a 1,095-day hole in one fund's NAV history despite
nav_history_backfilled_at being set, because that flag is one-time and
never revisited. lazy_nav_backfill.py now detects a real gap on each
fund view (a cheap local DB query) and attempts a repair, gated by this
timestamp so a permanent gap costs one wasted mfapi.in call per cooldown
window rather than one per page view forever.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '62269a9a0111'
down_revision: Union[str, Sequence[str], None] = '8bc03223c908'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('scheme_variants', sa.Column('nav_gap_repair_attempted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scheme_variants', 'nav_gap_repair_attempted_at')
