from typing import Any

from app import memory
from app.providers.base import ToolSpec

SEARCH_MEMORY = ToolSpec(
    name="search_memory",
    description=(
        "Busca en la memoria de incidentes pasados por similitud semantica con un "
        "sintoma. Devuelve los mas relevantes ya re-rankeados por recencia y calidad. "
        "Los incidentes obsoletos o reemplazados quedan fuera."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symptom": {"type": "string", "description": "El sintoma a buscar"},
            "service": {
                "type": "string",
                "description": "Opcional: acota la busqueda a un servicio",
            },
        },
        "required": ["symptom"],
    },
)

QUERY_INCIDENTS = ToolSpec(
    name="query_incidents",
    description=(
        "Consulta estructurada sobre los incidentes: los mas recientes de un servicio "
        "o de una severidad. Util para ver el contexto operativo, no la similitud."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "severity": {"type": "string", "enum": ["sev1", "sev2", "sev3", "sev4"]},
            "limit": {"type": "integer", "default": 10},
        },
    },
)

SUBMIT_DIAGNOSIS = ToolSpec(
    name="submit_diagnosis",
    description=(
        "Entrega el diagnostico final y termina. Si la memoria no aporto nada "
        "relevante, decilo explicitamente en root_cause y usa una confidence baja: "
        "no inventes una causa raiz."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "mitigation_steps": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["root_cause", "mitigation_steps", "confidence"],
    },
)

TOOLS = [SEARCH_MEMORY, QUERY_INCIDENTS, SUBMIT_DIAGNOSIS]


def _summarize(rows: list[dict]) -> list[dict]:
    keys = ("id", "title", "symptom", "root_cause", "resolution", "service", "score")
    return [
        {k: (round(v, 4) if isinstance(v, float) else str(v)) for k, v in row.items() if k in keys and v is not None}
        for row in rows
    ]


def cite_recalled(evidence: list) -> None:
    citados = {
        row["id"]
        for step in evidence
        if step.tool == SEARCH_MEMORY.name and isinstance(step.returned, list)
        for row in step.returned
        if isinstance(row, dict) and "id" in row
    }
    memory.cite(sorted(citados))


def run_tool(name: str, args: dict[str, Any]) -> tuple[Any, str]:
    if name == SEARCH_MEMORY.name:
        rows, via = memory.recall(args["symptom"], args.get("service"))
        return _summarize(rows), via
    if name == QUERY_INCIDENTS.name:
        rows, via = memory.query_incidents(
            args.get("service"), args.get("severity"), args.get("limit", 10)
        )
        return _summarize(rows), via
    raise ValueError(f"Herramienta desconocida: {name}")
