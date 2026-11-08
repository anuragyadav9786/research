"""amc portfolio disclosure schema gaps

Revision ID: 5def88399ca5
Revises: 368fd7d2b0e7
Create Date: 2026-11-07 09:50:17.861123

Closes schema gaps found by reading a real AMC monthly portfolio-
disclosure file (Aditya Birla Sun Life, September 2026) end to end:

- securities.isin becomes nullable -- a real disclosure always has a
  handful of rows with no ISIN at all (TREPS/reverse-repo, derivative
  margin, net receivable/payable), which are real money but aren't a
  security in the normal sense. Postgres allows any number of NULLs in
  a unique index, so this stays a safe join key for every real security.
- securities.instrument_type -- the broad category a disclosure's own
  section headers state (equity/debt/government security/etc.).
  Necessary, not just descriptive: the same "Industry^/Rating" column
  means an equity sector for an equity row but a credit rating for a
  debt row, and without this field there's no way to tell which one a
  given row's classification actually is.
- portfolio_holdings gains quantity, credit_rating, ytm_pct, ytc_pct --
  real fields every disclosure carries that nothing currently stores.
  credit_rating/ytm_pct/ytc_pct live on the holding (not the security)
  because they're point-in-time facts that can change between snapshots,
  not a permanent property of the instrument.

See docs/BUILD_PLAN.md open decision #2 and docs/data-sources.md's
"Planned sources" table -- AMC holdings ingestion is still not started;
this migration only closes the schema gap, not the ingestion pipeline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5def88399ca5'
down_revision: Union[str, Sequence[str], None] = '368fd7d2b0e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INSTRUMENT_TYPE_CHECK = (
    "instrument_type in ('equity', 'debt', 'government_security', 'securitised_debt', "
    "'money_market', 'mutual_fund_unit', 'reit_invit', 'foreign_security', "
    "'cash_equivalent', 'other')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('securities', 'isin', existing_type=sa.String(20), nullable=True)
    op.add_column('securities', sa.Column('instrument_type', sa.String(30), nullable=True))
    op.create_check_constraint('ck_security_instrument_type', 'securities', _INSTRUMENT_TYPE_CHECK)

    op.add_column('portfolio_holdings', sa.Column('quantity', sa.Numeric(20, 4), nullable=True))
    op.add_column('portfolio_holdings', sa.Column('credit_rating', sa.String(20), nullable=True))
    op.add_column('portfolio_holdings', sa.Column('ytm_pct', sa.Numeric(6, 3), nullable=True))
    op.add_column('portfolio_holdings', sa.Column('ytc_pct', sa.Numeric(6, 3), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('portfolio_holdings', 'ytc_pct')
    op.drop_column('portfolio_holdings', 'ytm_pct')
    op.drop_column('portfolio_holdings', 'credit_rating')
    op.drop_column('portfolio_holdings', 'quantity')

    op.drop_constraint('ck_security_instrument_type', 'securities', type_='check')
    op.drop_column('securities', 'instrument_type')
    op.alter_column('securities', 'isin', existing_type=sa.String(20), nullable=False)
