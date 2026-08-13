"""Persist a completed diagnosis.

Every write happens inside one transaction. A half-written diagnosis — a plant with
an observation but no diagnosis, or a diagnosis with no treatment plan — would show
up in the UI as a broken record with no way for the user to fix it.

Token usage and cost are read from the run-scoped collector on ``config`` and written
in that same transaction. A post-run ``UPDATE`` from the service would have been a
smaller change, but it splits one write into two: a crash between them leaves a
diagnosis with NULL cost, which is exactly the state ``M12`` describes (spec §2.2).
"""

import logging

from langchain_core.runnables import RunnableConfig

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.state import DiagnosisState
from core.cost import UsageSnapshot
from data.db import transaction

logger = logging.getLogger(__name__)


def _usage_from(config: RunnableConfig | None) -> UsageSnapshot | None:
    """The run's usage so far, or ``None`` when no collector was wired.

    ``None`` is the normal case for unit tests and for any caller that has not
    opted in, so this must never raise. By the time this node runs, every model
    call in the run has completed, so the snapshot is final.
    """
    if not config:
        return None
    collector = (config.get("configurable") or {}).get("usage_collector")
    return collector.snapshot() if collector is not None else None


def make_persist(deps: Deps) -> NodeFn:
    """Write the plant, observation, diagnosis and roadmap steps atomically."""

    def persist(state: DiagnosisState, config: RunnableConfig | None = None) -> dict:
        if state.differential is None:
            logger.info("nothing to persist: no differential was produced")
            return {"diagnosis_id": None}

        now = deps.now()
        observation_kind = "recheck" if state.plant_id is not None else "initial"

        with transaction(deps.plants.connection):
            plant_id = state.plant_id
            if plant_id is None:
                plant_id = deps.plants.create(
                    name=state.plant_name,
                    species=state.species_name,
                    species_confidence=state.species_confidence,
                    location_kind=state.location_kind,
                    location_text=state.location_text or state.answers.get("location"),
                    photo_ref=state.images[0].ref if state.images else None,
                    now=now,
                )
            elif state.species_name is not None:
                # A re-check of a plant that was never identified goes through
                # identify_plant (see route_after_quality) and can produce a species
                # here for the first time — persist it back onto the plant record.
                deps.plants.update_species(
                    plant_id,
                    species=state.species_name,
                    species_confidence=state.species_confidence,
                )

            observation_id = deps.observations.create(
                plant_id=plant_id,
                kind=observation_kind,
                photo_refs=[image.ref for image in state.images],
                user_notes=state.user_notes,
                now=now,
            )

            usage = _usage_from(config)
            diagnosis_id = deps.diagnoses.create(
                observation_id=observation_id,
                plant_id=plant_id,
                differential=state.differential,
                contagion=state.contagion,
                retrieved=state.retrieved,
                model=deps.settings.reasoning_model,
                now=now,
                token_usage=usage.as_token_usage() if usage else None,
                cost_usd=usage.cost_usd if usage else None,
            )

            if state.roadmap is not None:
                deps.roadmap.create_from_roadmap(
                    diagnosis_id=diagnosis_id,
                    plant_id=plant_id,
                    roadmap=state.roadmap,
                    now=now,
                )

        return {
            "plant_id": plant_id,
            "observation_id": observation_id,
            "diagnosis_id": diagnosis_id,
        }

    return persist
