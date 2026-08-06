"""Tests for corpus parsing and chunking."""

from pathlib import Path

import pytest

from knowledge.ingest import REQUIRED_SECTIONS, Chunk, load_corpus, parse_document

CORPUS = Path("knowledge/corpus")


def test_parse_document_yields_one_chunk_per_section():
    chunks = parse_document(CORPUS / "root-rot.md")
    sections = {c.section for c in chunks}
    assert sections >= REQUIRED_SECTIONS


def test_chunks_carry_frontmatter_metadata():
    chunks = parse_document(CORPUS / "spider-mites.md")
    assert all(c.doc_id == "spider-mites" for c in chunks)
    assert all(c.category == "pests" for c in chunks)
    assert all(c.transmissible is True for c in chunks)
    assert all(c.severity == "act_today" for c in chunks)


def test_non_transmissible_disorder_is_marked_false():
    chunks = parse_document(CORPUS / "root-rot.md")
    assert all(c.transmissible is False for c in chunks)


def test_section_text_excludes_the_heading():
    chunks = parse_document(CORPUS / "overwatering.md")
    symptoms = next(c for c in chunks if c.section == "Symptoms")
    assert not symptoms.text.startswith("#")
    assert "Yellowing leaves" in symptoms.text


def test_section_text_is_not_empty():
    chunks = parse_document(CORPUS / "root-rot.md")
    assert all(c.text.strip() for c in chunks)


def test_parse_document_rejects_a_missing_required_section(tmp_path):
    incomplete = tmp_path / "broken.md"
    incomplete.write_text(
        "---\nid: broken\nname: Broken\ncategory: pests\n"
        "transmissible: false\nseverity: monitor\n---\n\n"
        "## Symptoms\n\nSomething.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required section"):
        parse_document(incomplete)


def test_parse_document_rejects_missing_frontmatter_field(tmp_path):
    broken = tmp_path / "broken.md"
    broken.write_text("---\nid: broken\n---\n\n## Symptoms\n\nText.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter"):
        parse_document(broken)


def test_load_corpus_reads_every_document():
    chunks = load_corpus(CORPUS)
    doc_ids = {c.doc_id for c in chunks}
    assert {"root-rot", "overwatering", "spider-mites"} <= doc_ids
    assert all(isinstance(c, Chunk) for c in chunks)


def test_load_corpus_raises_on_an_empty_directory(tmp_path):
    with pytest.raises(ValueError, match="no documents"):
        load_corpus(tmp_path)
