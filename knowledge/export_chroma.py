"""Export the corpus vectors out of Chroma, once.

Run before the pgvector retriever replaces the Chroma one:

    uv run python -m knowledge.export_chroma

**Why export rather than re-embed.** Re-embedding the corpus would cost a fraction of a
cent and produce vectors that differ in their last bits — enough to make the parity gate
(``specs/disorder-retrieval``) a statistical comparison instead of an exact one. The
whole point of that gate is that any difference in retrieval is attributable to the new
SQL rather than to new numbers, so the numbers have to be the same numbers.

Reads the collection directly through ``chromadb`` rather than through LangChain's
wrapper: no embedding function is needed to read vectors that are already stored, and
constructing one would require an API key to do nothing with.
"""

import argparse
import json
import logging
from pathlib import Path

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("data/corpus_vectors.json")
COLLECTION = "plantopia"


def export(settings: Settings, output: Path) -> dict:
    """Write every stored chunk with its vector, and return a summary."""
    import chromadb

    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    collection = client.get_collection(COLLECTION)
    stored = collection.get(include=["embeddings", "documents", "metadatas"])

    ids = stored["ids"]
    embeddings = stored["embeddings"]
    documents = stored["documents"]
    metadatas = stored["metadatas"]

    if not ids:
        raise SystemExit(
            f"collection {COLLECTION!r} at {settings.chroma_path} is empty — "
            "there is nothing to export, and the parity gate has no baseline"
        )

    rows = [
        {
            "id": chunk_id,
            "doc_id": metadata["doc_id"],
            "section": metadata["section"],
            "content": document,
            "metadata": dict(metadata),
            "embedding": [float(x) for x in vector],
        }
        for chunk_id, vector, document, metadata in zip(
            ids, embeddings, documents, metadatas, strict=True
        )
    ]

    dimensions = {len(row["embedding"]) for row in rows}
    if len(dimensions) != 1:
        raise SystemExit(f"mixed embedding dimensions in one collection: {sorted(dimensions)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows), encoding="utf-8")

    summary = {
        "chunks": len(rows),
        "documents": len({row["doc_id"] for row in rows}),
        "dimensions": dimensions.pop(),
        "output": str(output),
    }
    logger.info("exported %s", summary)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = export(get_settings(), args.output)
    print(
        f"{summary['chunks']} chunks across {summary['documents']} documents "
        f"at {summary['dimensions']} dimensions -> {summary['output']}"
    )


if __name__ == "__main__":
    main()
