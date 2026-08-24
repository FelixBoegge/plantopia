"""The golden set: schema, loader, and corpus cross-checking.

Cases are text, not photographs. Every Ragas metric except top-1/top-3 is a
retrieval-and-generation metric that cannot see the vision layer, and the public
leaf-disease datasets originally proposed are crop pathology while this corpus
is houseplant disorders — so scoring against them would measure corpus scope rather
than agent quality (spec §3.1). The price is that vision accuracy goes unmeasured,
which the report states rather than hides.

One YAML file per case, mirroring the corpus's one-document-per-disorder layout so
cases diff and review individually.
"""

from pathlib import Path
from typing import Literal

import frontmatter
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.schemas import SymptomSet

CATEGORIES: frozenset[str] = frozenset(
    {"watering", "light", "nutrient", "pest", "fungal", "environmental", "other"}
)


class CasePlant(BaseModel):
    """The plant record a case implies, standing in for one the user would have."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    species: str | None = None
    location_kind: Literal["indoor", "outdoor"] = "indoor"
    location_text: str | None = None


class GoldenCase(BaseModel):
    """One evaluation case: a situation, its pre-written answers, and the truth."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str
    plant: CasePlant
    species_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    symptoms: SymptomSet
    answers: dict[str, str] = Field(default_factory=dict)
    # Clarifying questions are model-generated, so the set asked varies between runs
    # of the same case. Anything unmatched gets this rather than being left blank,
    # and the harness records which questions were actually asked (spec §3.4).
    default_answer: str = "not observed"
    ground_truth: str = Field(min_length=1)
    also_acceptable: list[str] = Field(default_factory=list)


def corpus_slugs(corpus_dir: Path) -> set[str]:
    """Every disorder id in the corpus, read from document frontmatter."""
    return {
        str(frontmatter.loads(path.read_text(encoding="utf-8"))["id"])
        for path in sorted(corpus_dir.glob("*.md"))
    }


def load_cases(directory: Path) -> list[GoldenCase]:
    """Parse every golden case in a directory, sorted by id.

    Raises:
        ValueError: if the directory holds no cases, or any case is malformed. The
            message names the file — a case that fails to parse must fail the suite
            rather than silently drop out of a metrics run.
    """
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise ValueError(f"no golden cases found in {directory}")

    cases: list[GoldenCase] = []
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            cases.append(GoldenCase.model_validate(raw))
        except ValidationError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
    return sorted(cases, key=lambda case: case.id)
