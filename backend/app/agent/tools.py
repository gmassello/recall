from typing import Any

from app import memory
from app.models import SEVERITIES
from app.providers.base import ToolSpec

SEARCH_MEMORY = ToolSpec(
    name="search_memory",
    description=(
        "Searches the memory of past repairs by semantic similarity with a symptom. "
        "Returns the most relevant ones already re-ranked by recency and quality. "
        "Outdated or superseded repairs are left out."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symptom": {"type": "string", "description": "The symptom to search for"},
            "service": {
                "type": "string",
                "description": "Optional: narrows the search to one shop area",
            },
        },
        "required": ["symptom"],
    },
)

QUERY_INCIDENTS = ToolSpec(
    name="query_incidents",
    description=(
        "Structured query over the repairs: the most recent ones from an area or a "
        "severity. Useful to see what the shop handled before, not similarity."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "service": {"type": "string"},
            "severity": {"type": "string", "enum": SEVERITIES},
            "limit": {"type": "integer", "default": 10},
        },
    },
)

SUBMIT_DIAGNOSIS = ToolSpec(
    name="submit_diagnosis",
    description=(
        "Delivers the final diagnosis and finishes. If memory contributed nothing "
        "relevant, say so explicitly in root_cause and use a low confidence: do not "
        "make up a root cause."
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
    cited = {
        row["id"]
        for step in evidence
        if step.tool == SEARCH_MEMORY.name and isinstance(step.returned, list)
        for row in step.returned
        if isinstance(row, dict) and "id" in row
    }
    memory.cite(sorted(cited))


def run_tool(name: str, args: dict[str, Any]) -> tuple[Any, str]:
    if name == SEARCH_MEMORY.name:
        rows, via = memory.recall(args["symptom"], args.get("service"))
        return _summarize(rows), via
    if name == QUERY_INCIDENTS.name:
        rows, via = memory.query_incidents(
            args.get("service"), args.get("severity"), args.get("limit", 10)
        )
        return _summarize(rows), via
    raise ValueError(f"Unknown tool: {name}")
