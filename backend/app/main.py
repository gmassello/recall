import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import incidents, memory, tickets
from app.config import settings
from app.mcp import cockroach_client

log = logging.getLogger(__name__)

app = FastAPI(title="Recall", version="0.1.0")

if not settings.demo_api_key:
    log.warning("DEMO_API_KEY is empty: the protected endpoints are open")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets.router)
app.include_router(incidents.router)
app.include_router(memory.router)


@app.get("/health")
def health(probe: bool = False) -> dict:
    if probe:
        return {"status": "ok", "mcp": cockroach_client.probe()}
    return {"status": "ok"}
