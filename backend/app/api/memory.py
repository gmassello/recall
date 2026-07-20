from fastapi import APIRouter

from app import memory
from app.models import Incident

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=list[Incident])
def inspect_memory(service: str | None = None) -> list[dict]:
    return memory.list_memory(service)
