"""weather series on observations

Revision ID: e0184af7c2f3
Revises: 8558cf4a3934
Create Date: 2026-08-31 16:17:08.782219

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 — generated Vector() columns reference it
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0184af7c2f3'
down_revision: Union[str, Sequence[str], None] = '8558cf4a3934'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The weather a diagnosis was made against, day by day, as a serialised
    # `WeatherSummary`. One column rather than a table: the series is always read whole,
    # always belongs to exactly one observation, and nothing queries across observations by
    # weather.
    #
    # Nullable, and every existing row keeps null — which is the true answer for all of
    # them. They were written when the weather was five aggregate numbers that went into a
    # prompt and were never kept. There is nothing to backfill from, and refetching would
    # invent a record of evidence a past diagnosis never saw.
    op.add_column("observations", sa.Column("weather_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("observations", "weather_json")
