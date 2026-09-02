"""progress verdict on diagnoses

Revision ID: a1c7e2f90b34
Revises: 53bce7d65e55
Create Date: 2026-09-02 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 — generated Vector() columns reference it
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e2f90b34'
down_revision: Union[str, Sequence[str], None] = '53bce7d65e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # How a re-check compared with the diagnosis before it: improving, static, worsening or
    # new_problem. The graph has always computed this to decide whether to revise the plan
    # or diagnose afresh, and then thrown it away — so the one screen where it matters, the
    # result somebody comes back to read, could not say which way their plant was going.
    #
    # Nullable, and null on every existing row, which is the true answer for all of them.
    # A first diagnosis has nothing to compare against and is null forever; a re-check made
    # before this column existed cannot say. Neither can be backfilled without inventing a
    # comparison nobody made.
    op.add_column("diagnoses", sa.Column("progress_verdict", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("diagnoses", "progress_verdict")
