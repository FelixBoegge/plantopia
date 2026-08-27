"""photograph metadata on observations

Revision ID: 8558cf4a3934
Revises: 79fc5cb7ddab
Create Date: 2026-08-27 08:56:20.768247

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 — generated Vector() columns reference it
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8558cf4a3934'
down_revision: Union[str, Sequence[str], None] = '79fc5cb7ddab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # What the photographs said about themselves, as distinct from what the upload said.
    #
    # All three nullable, and null means "no photograph declared it" rather than "not
    # known yet". Every row that already exists gets null, which is the true answer: they
    # were written when nothing read a photograph's metadata at all. There is nothing to
    # backfill from — the bytes that carried it were re-saved on the way in.
    op.add_column(
        "observations", sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Coarse by construction: `core/metadata.py` rounds to about eleven kilometres before
    # anything sees the value, so a precise position never reaches these columns. Two
    # floats rather than a geography type — nothing here does distance arithmetic, and the
    # weather lookup takes a pair of numbers.
    op.add_column("observations", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("observations", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("observations", "longitude")
    op.drop_column("observations", "latitude")
    op.drop_column("observations", "captured_at")
