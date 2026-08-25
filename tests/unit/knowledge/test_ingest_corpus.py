"""Loading the corpus into Postgres.

No API calls: rows are passed in directly, which is exactly how the ``--from-export``
path works. The embedding half is a one-shot deployment step and is exercised by the
row counts it produces, not by mocking the provider.
"""

import pytest
from sqlalchemy import func, select

from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
from knowledge.ingest_corpus import load


def _row(doc_id: str, section: str = "Symptoms", *, fill: float = 0.1) -> dict:
    return {
        "id": f"{doc_id}::{section}",
        "doc_id": doc_id,
        "section": section,
        "content": f"{doc_id} {section} text",
        "metadata": {
            "name": doc_id.replace("-", " ").title(),
            "category": "watering",
            "transmissible": False,
            "severity": "act_this_week",
        },
        "embedding": [fill] * EMBEDDING_DIMENSIONS,
    }


def test_rows_are_written(db):
    written = load([_row("overwatering"), _row("root-rot")], db)

    assert written == 2
    assert db.scalar(select(func.count()).select_from(CorpusChunk)) == 2


def test_a_document_contributes_one_row_per_section(db):
    load([_row("overwatering", "Symptoms"), _row("overwatering", "Look-alikes")], db)

    sections = db.scalars(
        select(CorpusChunk.section).where(CorpusChunk.doc_id == "overwatering")
    ).all()
    assert sorted(sections) == ["Look-alikes", "Symptoms"]


def test_reloading_replaces_rather_than_duplicates(db):
    """This is a deployment step, and a deployment step that is unsafe to repeat is one
    somebody will eventually repeat."""
    load([_row("overwatering", fill=0.1)], db)
    load([_row("overwatering", fill=0.2)], db)

    assert db.scalar(select(func.count()).select_from(CorpusChunk)) == 1
    stored = db.scalar(select(CorpusChunk).where(CorpusChunk.doc_id == "overwatering"))
    assert stored.embedding[0] == pytest.approx(0.2)


def test_vectors_of_the_wrong_width_are_refused(db):
    """Vectors from a different embedding model are not comparable with these ones, and
    pgvector would happily store them side by side."""
    wrong = _row("overwatering")
    wrong["embedding"] = [0.1] * 768

    with pytest.raises(SystemExit, match="768 dimensions"):
        load([wrong], db)


def test_nothing_is_written_when_one_row_is_malformed(db):
    """The width check runs over every row before the first insert, so a bad export
    cannot leave the corpus half-replaced."""
    wrong = _row("root-rot")
    wrong["embedding"] = [0.1] * 768

    with pytest.raises(SystemExit):
        load([_row("overwatering"), wrong], db)

    assert db.scalar(select(func.count()).select_from(CorpusChunk)) == 0
