"""species provenance

Revision ID: 79fc5cb7ddab
Revises: 28ce41499bec
Create Date: 2026-08-26 22:19:17.409541

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 — generated Vector() columns reference it
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79fc5cb7ddab'
down_revision: Union[str, Sequence[str], None] = '28ce41499bec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Where a diagnosis's species came from, and whether a person agreed to it.
    #
    # `species_method` is nullable and means *unknown* when null. Every row that already
    # exists gets null, which is the true answer: they were written when one method
    # produced the species and nothing recorded that it had. A backfill would have to
    # invent a provenance for them, in the one field whose purpose is telling a bad
    # identification apart from bad reasoning about a good one.
    op.add_column("diagnoses", sa.Column("species_method", sa.Text(), nullable=True))

    # `species_confirmed` is NOT NULL with a server default, because false is not a guess
    # here — nobody confirmed a diagnosis made before there was anything to confirm. The
    # server default rather than only the ORM's, so a row written by a repair script or a
    # later migration gets a value rather than failing the constraint.
    op.add_column(
        "diagnoses",
        sa.Column(
            "species_confirmed",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("diagnoses", "species_confirmed")
    op.drop_column("diagnoses", "species_method")
