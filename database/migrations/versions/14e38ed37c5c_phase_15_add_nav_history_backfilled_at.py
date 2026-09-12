"""phase 15 add nav_history_backfilled_at

Revision ID: 14e38ed37c5c
Revises: ffdc020aba6f
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14e38ed37c5c'
down_revision: Union[str, Sequence[str], None] = 'ffdc020aba6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'scheme_variants',
        sa.Column('nav_history_backfilled_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('scheme_variants', 'nav_history_backfilled_at')
