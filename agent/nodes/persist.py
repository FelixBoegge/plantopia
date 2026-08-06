"""Persist a completed diagnosis.

Every write happens inside one transaction. A half-written diagnosis — a plant with
an observation but no diagnosis, or a diagnosis with no treatment plan — would show
up in the UI as a broken record with no way for the user to fix it.
"""

import logging

from agent.deps import Deps
from agent.nodes.intake import NodeFn
from agent.state import DiagnosisState
from data.db import transaction

logger = logging.getLogger(__name__)


def make_persist(deps: Deps) -> NodeFn:
    """Write the plant, observation, diagnosis and roadmap steps atomically."""

    def persist(state: DiagnosisState) -> dict:
        if state.differential is None:
            logger.info("nothing to persist: no differential was produced")
            return {"diagnosis_id": None}

        now = deps.now()

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

            observation_id = deps.observations.create(
                plant_id=plant_id,
                kind="initial",
                photo_refs=[image.ref for image in state.images],
                user_notes=state.user_notes,
                now=now,
            )

            diagnosis_id = deps.diagnoses.create(
                observation_id=observation_id,
                plant_id=plant_id,
                differential=state.differential,
                contagion=state.contagion,
                retrieved=state.retrieved,
                model=deps.settings.reasoning_model,
                now=now,
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
