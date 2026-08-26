"""Species identification via Pl@ntNet.

A second opinion, from a specialist classifier over 50,000+ species rather than a
general-purpose vision model. Two methods built on different evidence either agree — which
is worth more than either alone — or disagree, which is a question for the person standing
in front of the plant.

**Every failure returns an empty list**, including a missing key. This is the first external
service on the diagnosis critical path that is not the model provider, and a diagnosis a
third party can stop is a diagnosis somebody paid for and did not get. No key, a timeout, a
429 past the free tier's daily allowance, a 4xx, a 5xx, a body that will not parse: all of
them mean the diagnosis proceeds on the vision model's identification alone, exactly as it
did before this file existed.

**The request shape was verified against the live service on 2026-08-26**, not taken from
documentation. That distinction is `U2`: a model slug read out of a docs fetch, flagged as
unverified because it might be wrong, which it was. Two readings of Pl@ntNet's own
documentation disagreed about whether ``habit`` is an accepted organ — the live service
settled it, and it is.

What the same call established, and what the tests here rest on:

- ``api-key`` and ``nb-results`` as query parameters; ``images`` and ``organs`` as multipart
  fields, one ``organs`` entry per image.
- Results are ranked, each with ``score`` and a ``species`` carrying
  ``scientificNameWithoutAuthor`` and ``commonNames``.
- An organ outside the vocabulary fails the **whole request** with a 400 rather than being
  ignored. Omitting ``organs`` entirely is accepted and lets the service detect them, which
  is what the retry below falls back on.

`tests/fixtures/plantnet_identify.json` is that response, recorded rather than written, and
every parsing test here is built from it.
"""

import logging

import httpx

from agent.schemas import ImageOrgan, SpeciesCandidate, SpeciesMethod

logger = logging.getLogger(__name__)

IDENTIFY_URL = "https://my-api.plantnet.org/v2/identify/all"

# 5 images and 50 MB per request, per the service's documentation. The pipeline's own upload
# limit is lower, but a diagnosis with more photographs than this must send some rather than
# fail, so it sends the first few.
MAX_IMAGES = 5

# Long enough for a classifier over a large corpus, short enough to be invisible inside a
# ninety-second run. A slow third party must cost latency, never the diagnosis.
_TIMEOUT = httpx.Timeout(15.0)

# What each organ is called on the wire. Kept as an explicit table rather than by taking the
# enum's value, so that the day the service's vocabulary and ours diverge is a one-line
# change here instead of a rename with callers.
#
# `UNKNOWN` is absent deliberately: it is ours, not theirs, and a photograph carrying it is
# sent with no claimed organ. Feeding a specialist classifier a guessed hint is worse than
# feeding it none.
WIRE_ORGANS: dict[ImageOrgan, str] = {
    ImageOrgan.LEAF: "leaf",
    ImageOrgan.FLOWER: "flower",
    ImageOrgan.FRUIT: "fruit",
    ImageOrgan.BARK: "bark",
    ImageOrgan.HABIT: "habit",
}

# What the service sends when the daily allowance is spent. Logged distinctly because "you
# have run out until tomorrow" and "something broke" want different responses from whoever
# reads the log — and identically otherwise, because the diagnosis does the same thing.
_QUOTA_STATUS = 429

# What the service answers when the request itself is malformed — which, confirmed against
# the real service, includes naming an organ outside its vocabulary. See the retry below.
_BAD_REQUEST_STATUS = 400


def identify_species(
    photographs: list[tuple[bytes, ImageOrgan]],
    *,
    api_key: str | None,
    max_results: int = 3,
    client: httpx.Client | None = None,
    omit_organs: bool = False,
) -> list[SpeciesCandidate]:
    """Ask Pl@ntNet what the plant is.

    Args:
        photographs: The image bytes and the organ each one shows.
        api_key: The credential. ``None`` means the service is not configured, and no
            request is made — not a failed one, none at all.
        max_results: How many candidates to ask for.
        client: Optional httpx client, for connection reuse.
        omit_organs: Send no organs at all, letting the service detect them. The escape
            hatch for the unverified vocabulary described in this module's docstring: the
            service's documentation says an absent ``organs`` treats every image as
            automatic, so this is the shape that cannot be rejected for naming a value.

    Returns:
        Candidates ranked most likely first, or an empty list. Never raises.
    """
    if not api_key or not photographs:
        return []

    owns_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT)
    try:
        chosen = photographs[:MAX_IMAGES]
        if len(photographs) > MAX_IMAGES:
            logger.info(
                "sending %d of %d photographs to plantnet: the service accepts %d",
                MAX_IMAGES,
                len(photographs),
                MAX_IMAGES,
            )

        files = [
            ("images", (f"photo-{index}.jpg", data, "image/jpeg"))
            for index, (data, _) in enumerate(chosen)
        ]
        if not omit_organs:
            files.extend(
                ("organs", (None, WIRE_ORGANS[organ]))
                for _, organ in chosen
                if organ in WIRE_ORGANS
            )

        params = {"api-key": api_key, "nb-results": max_results}
        response = client.post(IDENTIFY_URL, params=params, files=files)

        if response.status_code == _QUOTA_STATUS:
            logger.warning("plantnet daily allowance is spent; proceeding without it")
            return []

        # An organ the service does not recognise fails the *whole request* with a 400
        # rather than being ignored — confirmed against the real service, which is what
        # makes this worth handling rather than assuming. Left alone, a single wrong value
        # in `WIRE_ORGANS` would disable identification for every diagnosis, silently and
        # for ever, while every unit test went on passing.
        #
        # So one retry without organs. The answer is slightly worse — the service detects
        # the organs itself — and slightly worse beats absent.
        if response.status_code == _BAD_REQUEST_STATUS and not omit_organs:
            logger.warning(
                "plantnet refused the request; retrying without organs. "
                "If this persists, an organ in WIRE_ORGANS is not one the service accepts."
            )
            response = client.post(
                IDENTIFY_URL,
                params=params,
                files=[entry for entry in files if entry[0] != "organs"],
            )

        response.raise_for_status()
        return _candidates(response.json(), max_results)
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.warning("plantnet identification failed: %s", exc)
        return []
    finally:
        if owns_client:
            client.close()


def _candidates(body: object, limit: int) -> list[SpeciesCandidate]:
    """Read the ranked results out of a response.

    Tolerant on the way in: a result missing a name or a score is skipped rather than
    failing the batch, because a partial answer from a second opinion is still a second
    opinion. Anything that is not the shape expected at all raises, and the caller turns
    that into an empty list like any other failure.
    """
    if not isinstance(body, dict):
        raise ValueError("plantnet response was not an object")

    found: list[SpeciesCandidate] = []
    for result in body.get("results", [])[:limit]:
        species = result.get("species") or {}
        # A common name where there is one: "Basil" is what somebody calls their plant, and
        # `Ocimum basilicum L.` is not. The scientific name is kept alongside rather than
        # instead, because it is what makes two spellings of the same plant comparable.
        common = next(iter(species.get("commonNames") or []), None)
        scientific = species.get("scientificNameWithoutAuthor") or species.get("scientificName")
        name = common or scientific
        score = result.get("score")

        if not name or not isinstance(score, int | float):
            continue

        found.append(
            SpeciesCandidate(
                common_name=name,
                scientific_name=scientific,
                confidence=max(0.0, min(1.0, float(score))),
                method=SpeciesMethod.PLANTNET,
            )
        )
    return found
