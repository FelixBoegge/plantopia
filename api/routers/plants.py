"""An owner's plants.

Every handler takes the owner from the dependency and passes it into the service. None
reads an identifier from the path and acts on it alone — that is the rule the whole
tenancy story rests on, and it is visible in every signature below.
"""

from uuid import UUID

from fastapi import APIRouter, status

from api import converters
from api.dependencies import OwnerDep, PlantServiceDep
from api.schemas import PlantDetailOut, PlantSummaryOut, RenamePlantIn
from data.repositories.errors import RecordNotFoundError

router = APIRouter(prefix="/plants", tags=["plants"])


@router.get("", response_model=list[PlantSummaryOut])
def list_plants(service: PlantServiceDep, owner: OwnerDep) -> list[PlantSummaryOut]:
    """Every plant this owner has, newest first."""
    return [converters.plant_summary(summary) for summary in service.list_plants()]


@router.get("/{plant_id}", response_model=PlantDetailOut)
def get_plant(plant_id: UUID, service: PlantServiceDep, owner: OwnerDep) -> PlantDetailOut:
    """One plant with its history.

    Raises ``RecordNotFoundError`` — mapped to 404 — when the plant is unknown *or*
    belongs to somebody else. The service returns ``None`` for both, which is what makes
    the two indistinguishable from outside.
    """
    detail = service.get_plant_detail(plant_id)
    if detail is None:
        raise RecordNotFoundError(f"no plant {plant_id}")
    return converters.plant_detail(detail)


@router.patch("/{plant_id}", response_model=PlantDetailOut)
def rename_plant(
    plant_id: UUID, body: RenamePlantIn, service: PlantServiceDep, owner: OwnerDep
) -> PlantDetailOut:
    """Give a plant the name its owner calls it.

    Not its species: what an owner calls a plant and what it is are separate, and
    confirming one must not overwrite the other.
    """
    service.rename_plant(plant_id, name=body.name)
    detail = service.get_plant_detail(plant_id)
    if detail is None:  # pragma: no cover — rename would have raised first
        raise RecordNotFoundError(f"no plant {plant_id}")
    return converters.plant_detail(detail)


@router.delete("/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plant(plant_id: UUID, service: PlantServiceDep, owner: OwnerDep) -> None:
    """Remove a plant and everything hanging off it."""
    service.delete_plant(plant_id)
