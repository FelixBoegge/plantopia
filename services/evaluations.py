"""Reading what the evaluation harness last produced.

A file on disk, written by a command somebody runs by hand. The API reads it rather than
running anything: a harness run costs real money and takes minutes, which makes it a
different kind of thing from a page that renders a result.

**No harness having run is not an error.** It is the ordinary state of a fresh clone, and a
page that failed there would send somebody looking for a bug instead of a command.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The newest result, or the absence of one."""

    generated_at: str | None
    results: dict | None

    @property
    def exists(self) -> bool:
        return self.results is not None


NOTHING_YET = Evaluation(generated_at=None, results=None)


def latest(directory: Path) -> Evaluation:
    """The most recent result the harness wrote.

    Newest by filename, which the harness stamps with an ISO timestamp — so the ordering is
    the same whether or not the filesystem preserves modification times, which a checkout
    does not.

    A file that cannot be read is reported as nothing rather than raised. The alternative is
    an admin page that fails because one old result was truncated by a full disk.
    """
    if not directory.exists():
        return NOTHING_YET

    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            results = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("could not read evaluation result %s; trying the one before", path)
            continue
        return Evaluation(generated_at=results.get("generated_at"), results=results)

    return NOTHING_YET
