"""Parse the disorder corpus into retrievable chunks.

Chunking is per section, not per character count. The diagnose node reasons over
the look-alike and confirming-test sections specifically, so blending them into
fixed-size windows would destroy the structure that makes the corpus useful.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

REQUIRED_SECTIONS: frozenset[str] = frozenset(
    {
        "Symptoms",
        "Where on the plant symptoms appear",
        "Look-alikes and how to tell them apart",
        "Confirming test the user can perform",
        "Treatment, least-invasive first",
        "Expected time to visible improvement",
        "Prognosis and when to give up",
    }
)

REQUIRED_FRONTMATTER: frozenset[str] = frozenset(
    {"id", "name", "category", "transmissible", "severity"}
)

_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Chunk:
    """One section of one disorder document."""

    doc_id: str
    name: str
    section: str
    text: str
    category: str
    transmissible: bool
    severity: str


def parse_document(path: Path) -> list[Chunk]:
    """Parse a single corpus document into one chunk per section.

    Raises:
        ValueError: if frontmatter fields or required sections are missing.
    """
    post = frontmatter.loads(path.read_text(encoding="utf-8"))

    missing_meta = REQUIRED_FRONTMATTER - set(post.metadata)
    if missing_meta:
        raise ValueError(f"{path.name}: frontmatter is missing {sorted(missing_meta)}")

    sections = _split_sections(post.content)

    missing_sections = REQUIRED_SECTIONS - set(sections)
    if missing_sections:
        raise ValueError(f"{path.name}: missing required section(s) {sorted(missing_sections)}")

    return [
        Chunk(
            doc_id=str(post["id"]),
            name=str(post["name"]),
            section=heading,
            text=body,
            category=str(post["category"]),
            transmissible=bool(post["transmissible"]),
            severity=str(post["severity"]),
        )
        for heading, body in sections.items()
    ]


def _split_sections(content: str) -> dict[str, str]:
    """Split markdown into ``{heading: body}`` on level-two headings."""
    matches = list(_SECTION_RE.finditer(content))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        if body:
            sections[match.group(1).strip()] = body
    return sections


def load_corpus(corpus_dir: Path) -> list[Chunk]:
    """Parse every markdown document in the corpus directory.

    Raises:
        ValueError: if the directory contains no documents.
    """
    paths = sorted(corpus_dir.glob("*.md"))
    if not paths:
        raise ValueError(f"no documents found in {corpus_dir}")

    chunks: list[Chunk] = []
    for path in paths:
        chunks.extend(parse_document(path))
    return chunks


def chunk_text(chunk: Chunk) -> str:
    """The text that gets embedded for a chunk.

    One definition, used by both the Chroma builder and the pgvector ingestion. A
    second copy that drifted by a character would produce different vectors, and the
    corpus would quietly stop matching what the parity fixture recorded.
    """
    return f"{chunk.name} — {chunk.section}\n\n{chunk.text}"
