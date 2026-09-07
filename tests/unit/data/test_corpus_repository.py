"""Looking a disorder's display name up by its id.

The corpus is the one table with no owner, so this is the one repository that takes no
`user_id` — `data/models.CorpusChunk` says why: it is reference data, identical for
everybody and unchanged by anything anybody does.

It exists because a stored `Passage` carries `doc_id` and not a name, and the slug is not
the name: three of the 43 documents disagree with it (`botrytis` is "Botrytis (grey
mould)", `pot-bound` is "Pot-bound (root-bound)", `damping-off` keeps its hyphen). Deriving
a name from the slug would invent two of those and mangle the third.
"""

from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
from data.repositories.corpus import CorpusRepository

SYMPTOMS = "Symptoms"
LOOKALIKES = "Look-alikes and how to tell them apart"


def _chunk(doc_id: str, name: str, section: str = SYMPTOMS) -> CorpusChunk:
    return CorpusChunk(
        doc_id=doc_id,
        section=section,
        name=name,
        content=f"{doc_id} / {section}",
        category="watering",
        transmissible=False,
        severity="act_this_week",
        embedding=[0.0] * EMBEDDING_DIMENSIONS,
    )


def test_names_come_back_keyed_by_doc_id(db):
    db.add_all(
        [
            _chunk("overwatering", "Overwatering"),
            _chunk("botrytis", "Botrytis (grey mould)"),
        ]
    )
    db.flush()

    found = CorpusRepository(db).names_for(["overwatering", "botrytis"])

    assert found == {"overwatering": "Overwatering", "botrytis": "Botrytis (grey mould)"}


def test_one_name_per_document_however_many_sections_it_has(db):
    """Every section of a document carries the same name, and a caller wants the document."""
    db.add_all(
        [
            _chunk("root-rot", "Root rot", SYMPTOMS),
            _chunk("root-rot", "Root rot", LOOKALIKES),
        ]
    )
    db.flush()

    assert CorpusRepository(db).names_for(["root-rot"]) == {"root-rot": "Root rot"}


def test_a_document_that_is_no_longer_in_the_corpus_is_simply_absent(db):
    """Not an error, and not a blank. An old diagnosis can cite a disorder since renamed or
    removed; the caller decides what to show, and it must be able to tell that it has
    nothing rather than be handed an empty string."""
    db.add(_chunk("overwatering", "Overwatering"))
    db.flush()

    found = CorpusRepository(db).names_for(["overwatering", "disorder-that-was-deleted"])

    assert found == {"overwatering": "Overwatering"}


def test_asking_for_nothing_reads_nothing(db):
    """A diagnosis with no retrieved passages must not become a query for every row."""
    assert CorpusRepository(db).names_for([]) == {}
