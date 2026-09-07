"""What a diagnosis consulted, named for a reader.

The passages are already on the stored diagnosis — `retrieved_refs_json` has carried
`doc_id`, `section`, the text and the score since the first diagnosis was written. What was
missing was any way to read them: nothing put them on `DiagnosisOut` (`U23`).

Two things have to be resolved before a screen can show them. A `doc_id` is a slug and not
a name, so the name is looked up from the corpus. And a passage's origin matters more than
its score: `retrieved` mixes corpus cosine scores with Tavily relevance scores after web
escalation (`M4`), which are not comparable — so provenance is what a reader is given, and
the score is not shown at all.
"""

from agent.schemas import Passage
from data.models import EMBEDDING_DIMENSIONS, CorpusChunk
from data.repositories.corpus import CorpusRepository
from services.plant_service import KNOWLEDGE_BASE, WEB, sources_of

SYMPTOMS = "Symptoms"


def _corpus(db, *documents: tuple[str, str]) -> dict[str, str]:
    db.add_all(
        [
            CorpusChunk(
                doc_id=doc_id,
                section=SYMPTOMS,
                name=name,
                content=f"{doc_id} / {SYMPTOMS}",
                category="watering",
                transmissible=False,
                severity="act_this_week",
                embedding=[0.0] * EMBEDDING_DIMENSIONS,
            )
            for doc_id, name in documents
        ]
    )
    db.flush()
    return CorpusRepository(db).names_for([doc_id for doc_id, _ in documents])


def _passage(doc_id: str, section: str = SYMPTOMS, score: float = 0.5) -> Passage:
    return Passage(doc_id=doc_id, section=section, text="…", score=score)


def test_a_corpus_passage_is_named_from_the_corpus(db):
    names = _corpus(db, ("botrytis", "Botrytis (grey mould)"))

    found = sources_of([_passage("botrytis")], names)

    assert [(s.name, s.section, s.origin) for s in found] == [
        ("Botrytis (grey mould)", SYMPTOMS, KNOWLEDGE_BASE)
    ]


def test_a_web_passage_is_named_by_its_host(db):
    """`tools/web_search` keys a web result as `web:{host}` and puts the page title in the
    section. A reader is owed the site it came from, because that is what makes it
    weigh differently from the curated corpus."""
    found = sources_of(
        [_passage("web:rhs.org.uk", section="Caring for Calathea")],
        {},
    )

    assert [(s.name, s.section, s.origin) for s in found] == [
        ("rhs.org.uk", "Caring for Calathea", WEB)
    ]


def test_a_disorder_no_longer_in_the_corpus_keeps_its_slug(db):
    """Better a slug than a blank row or a dropped one. An old diagnosis genuinely cited
    it, and silently omitting it would understate what the model read."""
    found = sources_of([_passage("disorder-since-removed")], {})

    assert [(s.name, s.origin) for s in found] == [("disorder-since-removed", KNOWLEDGE_BASE)]


def test_the_order_retrieval_returned_is_kept(db):
    """The first six are similarity-ranked and the rest were fetched by id once a disorder
    was in contention. Re-sorting would present a deliberate fetch as a weak match."""
    names = _corpus(db, ("overwatering", "Overwatering"), ("root-rot", "Root rot"))

    found = sources_of(
        [_passage("root-rot", score=0.61), _passage("overwatering", score=0.59)],
        names,
    )

    assert [s.name for s in found] == ["Root rot", "Overwatering"]


def test_every_consulted_passage_is_listed_including_the_unranked_ones(db):
    """Twelve of eighteen on a real diagnosis score 0.0 because nothing ranked them — they
    were fetched by id, mostly each candidate's look-alikes section. They are most of what
    the model actually read, so a score of zero must not read as "not consulted"."""
    names = _corpus(db, ("overwatering", "Overwatering"))

    found = sources_of(
        [
            _passage("overwatering", score=0.59),
            _passage("overwatering", section="Look-alikes", score=0.0),
        ],
        names,
    )

    assert [s.section for s in found] == [SYMPTOMS, "Look-alikes"]


def test_nothing_retrieved_is_no_sources(db):
    assert sources_of([], {}) == []
