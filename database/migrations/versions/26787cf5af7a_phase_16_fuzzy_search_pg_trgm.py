"""phase 16 fuzzy search pg_trgm

Revision ID: 26787cf5af7a
Revises: 14e38ed37c5c
Create Date: 2026-09-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '26787cf5af7a'
down_revision: Union[str, Sequence[str], None] = '14e38ed37c5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enables similarity()/word_similarity() and the trigram GIN index type
    # used below, so fund search can tolerate typos instead of only exact
    # substring (ILIKE) matches.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_schemes_name_trgm ON schemes USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_schemes_name_trgm")
    # Extension left in place on downgrade: other objects may depend on it
    # and CREATE EXTENSION IF NOT EXISTS above is itself idempotent.
