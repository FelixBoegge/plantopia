"""Put the disorder corpus into Postgres, with its embeddings.

    uv run python -m knowledge.ingest_corpus                 # embed the corpus
    uv run python -m knowledge.ingest_corpus --from-export   # reuse exported vectors

Two sources, because they answer different questions. **Embedding** is what a
deployment does: read the corpus, call the embedding API once per section, store the
result. **Loading an export** is what the migration does: the vectors Chroma already
held, byte for byte, so the parity gate compares retrieval rather than comparing two
sets of numbers that happen to be close.

Idempotent: the corpus is keyed by ``(doc_id, section)``, so re-running replaces each
row rather than accumulating duplicates. That matters because this is a deployment
step, and a deployment step that is unsafe to repeat is a deployment step someone will
eventually repeat.

Makes no model calls. The vectors come from ``knowledge.export_chroma``, which is the
whole reason the parity gate can compare exactly rather than approximately.
"""

import argparse
import json
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from agent.wiring import open_session
from core.config import get_settings
from data.engine import transaction
from data.models import EMBEDDING_DIMENSIONS, CorpusChunk

logger = logging.getLogger(__name__)

DEFAULT_INPUT = Path("data/corpus_vectors.json")


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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--from-export",
        action="store_true",
        help="load exported Chroma vectors instead of embedding the corpus",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.from_export:
        if not args.input.exists():
            raise SystemExit(
                f"{args.input} does not exist — run `python -m knowledge.export_chroma` first"
            )
        rows = json.loads(args.input.read_text(encoding="utf-8"))
    else:
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
