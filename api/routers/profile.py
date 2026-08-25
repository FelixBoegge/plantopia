"""What has been learned about the owner.

A record of the inferences a system holds about a person belongs somewhere that person
can reach and remove, which is why forgetting is an endpoint rather than a support
request.
"""

from fastapi import APIRouter, status

from api import converters
from api.dependencies import OwnerDep, ProfileServiceDep
from api.schemas import ForgetFactIn, ProfileFactOut

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/facts", response_model=list[ProfileFactOut])
def list_facts(service: ProfileServiceDep, owner: OwnerDep) -> list[ProfileFactOut]:
    """Every fact held about this owner, unfiltered.

    Including low-confidence ones: this is the view that says what the system believes,
    and hiding the weakly-held beliefs would make it a summary rather than a record.
    """
    return [converters.profile_fact(fact) for fact in service.all_facts()]


@router.post("/facts/forget", status_code=status.HTTP_204_NO_CONTENT)
def forget_fact(body: ForgetFactIn, service: ProfileServiceDep, owner: OwnerDep) -> None:
    """Delete a fact the owner says is wrong.

    A POST rather than a DELETE with the fact in the path: a fact is a sentence, and
    sentences do not belong in URLs — they are logged, cached and shoulder-surfable in a
    way a request body is not.

    Forgetting something not held succeeds. The desired state already holds, and an error
    would only tell the owner something about what is stored that they did not ask.
    """
    service.forget(body.fact)
