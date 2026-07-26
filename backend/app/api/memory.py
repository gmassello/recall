from fastapi import APIRouter, HTTPException

from app import memory
from app.models import Incident, IncidentUpdate, SupersedeRequest

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=list[Incident])
def inspect_memory(service: str | None = None) -> list[dict]:
    return memory.list_memory(service)


@router.patch("/memory/{incident_id}", response_model=Incident)
def edit_memory(incident_id: str, body: IncidentUpdate) -> dict:
    row = memory.update_incident(incident_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return row


@router.delete("/memory/{incident_id}", status_code=204)
def delete_memory(incident_id: str) -> None:
    if not memory.delete_incident(incident_id):
        raise HTTPException(status_code=404, detail="Incident not found")


@router.delete("/memory")
def clear_memory() -> dict:
    return {"deleted": memory.clear_memory()}


@router.post("/memory/{incident_id}/supersede", status_code=204)
def supersede_memory(incident_id: str, body: SupersedeRequest) -> None:
    if not memory.supersede(incident_id, body.new_id):
        raise HTTPException(status_code=404, detail="Incident not found")
