from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app import memory
from app.api.deps import require_api_key
from app.models import Incident, IncidentUpdate, SupersedeRequest

router = APIRouter(tags=["memory"])
protected = [Depends(require_api_key)]


@router.get("/memory", response_model=list[Incident])
def inspect_memory(service: str | None = None) -> list[dict]:
    return memory.list_memory(service)


@router.patch("/memory/{incident_id}", response_model=Incident, dependencies=protected)
def edit_memory(incident_id: UUID, body: IncidentUpdate) -> dict:
    row = memory.update_incident(str(incident_id), body.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return row


@router.delete("/memory/{incident_id}", status_code=204, dependencies=protected)
def delete_memory(incident_id: UUID) -> None:
    if not memory.delete_incident(str(incident_id)):
        raise HTTPException(status_code=404, detail="Incident not found")


@router.delete("/memory", dependencies=protected)
def clear_memory() -> dict:
    return {"deleted": memory.clear_memory()}


@router.post("/memory/{incident_id}/supersede", status_code=204, dependencies=protected)
def supersede_memory(incident_id: UUID, body: SupersedeRequest) -> None:
    if not memory.supersede(str(incident_id), str(body.new_id)):
        raise HTTPException(status_code=404, detail="Incident not found")
