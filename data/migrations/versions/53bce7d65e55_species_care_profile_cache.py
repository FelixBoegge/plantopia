"""species care profile cache

Revision ID: 53bce7d65e55
Revises: e0184af7c2f3
Create Date: 2026-08-31 21:45:36.319668

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 — generated Vector() columns reference it
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53bce7d65e55'
down_revision: Union[str, Sequence[str], None] = 'e0184af7c2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Researched care baselines, cached once per species.
    #
    # **No `user_id`, and that is deliberate** — the same argument `corpus_chunks` makes.
    # What a species wants is the same fact for everybody, and scoping this per owner would
    # mean researching the same plant again for every account that photographs one, which is
    # the cost the cache exists to avoid. Nothing personal is stored here: a species name and
    # public care guidance.
    #
    # Keyed by the normalised name rather than a generated id, because the name is the
    # identity — there is exactly one row per species and nothing looks one up any other way.
    op.create_table(
        "species_care_profiles",
        sa.Column("species_key", sa.Text(), nullable=False),
        sa.Column("species", sa.Text(), nullable=False),
        sa.Column("light", sa.Text(), nullable=False),
        sa.Column("water", sa.Text(), nullable=False),
        sa.Column("temperature_min_c", sa.Integer(), nullable=False),
        sa.Column("temperature_max_c", sa.Integer(), nullable=False),
        sa.Column("humidity", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("species_key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("species_care_profiles")
