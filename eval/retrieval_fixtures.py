"""Reading and writing the retrieval parity fixture.

Shared by the capture script and the test, so the two cannot disagree about the format.

**Vectors are stored as base64 float32.** As JSON numbers the same 87 vectors take 2.8 MB,
which is a lot to carry in a repository forever for something read by one test. The
narrowing is *lossless* here, and demonstrably so: the embedding API returns float32, so
every stored value already round-trips through float32 exactly — `test_retrieval_parity`
asserts that rather than trusting it.
"""

import base64
import json
import struct
from pathlib import Path

FIXTURE_PATH = Path("eval/fixtures/retrieval_parity.json")


def encode_vector(vector: list[float]) -> str:
    """Pack a vector into base64 float32."""
    return base64.b64encode(struct.pack(f"{len(vector)}f", *vector)).decode("ascii")


def decode_vector(encoded: str) -> list[float]:
    """Unpack what ``encode_vector`` wrote."""
    raw = base64.b64decode(encoded)
    return list(struct.unpack(f"{len(raw) // 4}f", raw))


def load(path: Path = FIXTURE_PATH) -> dict:
    """The fixture, with vectors decoded."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing — run `python -m eval.capture_retrieval_fixtures` "
            "against the Chroma retriever before it is removed"
        )
    fixture = json.loads(path.read_text(encoding="utf-8"))
    for search in [*fixture["searches"], *fixture.get("escalation_probes", [])]:
        if search.get("vector"):
            search["vector"] = decode_vector(search["vector"])
    return fixture


def dump(fixture: dict, path: Path = FIXTURE_PATH) -> None:
    """Write the fixture, encoding vectors on the way out."""
    encoded = dict(fixture)
    for key in ("searches", "escalation_probes"):
        if key in fixture:
            encoded[key] = [
                {**s, "vector": encode_vector(s["vector"])} if s.get("vector") else s
                for s in fixture[key]
            ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(encoded), encoding="utf-8")
