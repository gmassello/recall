from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import incidents, memory, tickets
from app.config import settings
from app.mcp import cockroach_client

app = FastAPI(title="Recall", version="0.1.0")

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
def health() -> dict:
    return {"status": "ok", "mcp": cockroach_client.probe()}
