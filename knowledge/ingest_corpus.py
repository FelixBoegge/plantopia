"""Put the disorder corpus into Postgres, with its embeddings.

    uv run python -m knowledge.ingest_corpus

Reads the corpus, embeds each section, stores the result. Costs a fraction of a cent
for 301 sections.

Nothing reads this table yet: retrieval still runs on Chroma. The table and this
command exist because the retrieval move is deliberately deferred until the embedding
model is chosen — see `docs/known-limitations.md`. Changing model means re-running this,
and vectors from two models are not comparable, so it replaces rather than appends.

Idempotent: the corpus is keyed by ``(doc_id, section)``, so re-running replaces each
row rather than accumulating duplicates. That matters because this is a deployment
step, and a deployment step that is unsafe to repeat is a deployment step someone will
eventually repeat.

**This makes model calls.** One embedding request per batch, for 301 sections — about
$0.0005. It embeds the corpus itself rather than copying vectors from anywhere else; the
export that once seeded them from Chroma, and the parity gate it fed, were deleted in
``ddcea71``.
"""

import argparse
import logging

from sqlalchemy.dialects.postgresql import insert

from agent.wiring import open_session
from core.config import get_settings
from data.engine import transaction
from data.models import EMBEDDING_DIMENSIONS, CorpusChunk

logger = logging.getLogger(__name__)


def rows_from_corpus(settings) -> list[dict]:
    """Embed every corpus section. Costs one API call per batch and a fraction of a cent."""
    from core.llm import build_embeddings
    from knowledge.ingest import chunk_text, load_corpus

    chunks = load_corpus(settings.corpus_path)
    embeddings = build_embeddings()
    # The same text build_vectorstore embedded for Chroma. It has to stay identical:
    # a different string is a different vector, and the corpus would silently stop
    # matching what the parity fixture recorded.
    texts = [chunk_text(c) for c in chunks]
    vectors = embeddings.embed_documents(texts)
    return [
        {
            "id": f"{chunk.doc_id}::{chunk.section}",
            "doc_id": chunk.doc_id,
            "section": chunk.section,
            "content": text,
            "metadata": {
                "name": chunk.name,
                "category": chunk.category,
                "transmissible": chunk.transmissible,
                "severity": chunk.severity,
            },
            "embedding": vector,
        }
        for chunk, text, vector in zip(chunks, texts, vectors, strict=True)
    ]


def load(rows: list[dict], session) -> int:
    """Upsert every exported chunk. Returns how many were written."""
    for row in rows:
        vector = row["embedding"]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise SystemExit(
                f"{row['id']} has {len(vector)} dimensions, expected {EMBEDDING_DIMENSIONS} — "
                "these vectors came from a different embedding model"
            )

    with transaction(session):
        for row in rows:
            metadata = row["metadata"]
            statement = (
                insert(CorpusChunk)
                .values(
                    doc_id=row["doc_id"],
                    section=row["section"],
                    name=metadata["name"],
                    content=row["content"],
                    category=metadata["category"],
                    transmissible=metadata["transmissible"],
                    severity=metadata["severity"],
                    embedding=row["embedding"],
                )
                .on_conflict_do_update(
                    index_elements=[CorpusChunk.doc_id, CorpusChunk.section],
                    set_={
                        "name": metadata["name"],
                        "content": row["content"],
                        "category": metadata["category"],
                        "transmissible": metadata["transmissible"],
                        "severity": metadata["severity"],
                        "embedding": row["embedding"],
                    },
                )
            )
            session.execute(statement)
    return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    settings = get_settings()
    rows = rows_from_corpus(settings)
    session = open_session(settings)
    try:
        written = load(rows, session)
    finally:
        session.close()

    documents = len({row["doc_id"] for row in rows})
    print(f"loaded {written} chunks across {documents} documents")


if __name__ == "__main__":
    main()
