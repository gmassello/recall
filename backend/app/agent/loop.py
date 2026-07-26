import logging
from collections.abc import Iterator

from pydantic import ValidationError

from app.agent.tools import SUBMIT_DIAGNOSIS, TOOLS, cite_recalled, run_tool
from app.config import settings
from app.models import Diagnosis, EvidenceStep, HandleResponse, RelevantIncident
from app.providers.base import Message, ToolResult
from app.providers.registry import get_llm

log = logging.getLogger(__name__)

SYSTEM = """You are the technician at a computer and phone repair shop. You get the
ticket of a device that came into the shop and you have to diagnose it using the
memory of past repairs.

Procedure:
1. Use search_memory with the symptom from the ticket. It is your main source.
2. If you need to see what was repaired before in that area, use query_incidents.
3. You ALWAYS finish by calling submit_diagnosis.

The rule that never breaks: if memory returned nothing similar, say so in root_cause
and set a low confidence. An "I have no precedent for this" is a correct answer; a
made-up root cause is not."""

NO_CONTENT = "(no content)"

DIAGNOSIS_REQUEST = (
    "You did not call any tool. If you already have what you need, call "
    "submit_diagnosis; if you are missing context, use search_memory or query_incidents."
)

PREMATURE_DIAGNOSIS = {
    "error": (
        "You called submit_diagnosis in the same turn as other tools, so you have "
        "not seen what they returned yet. The diagnosis was discarded. Review the "
        "results of this turn and call submit_diagnosis again."
    )
}

NO_DIAGNOSIS = Diagnosis(
    root_cause="The agent did not reach a diagnosis within the turn limit.",
    mitigation_steps=["Review the ticket manually."],
    confidence=0.0,
)


def _prompt(ticket: dict) -> str:
    return (
        f"Ticket: {ticket['title']}\n"
        f"Service: {ticket.get('service') or 'unknown'}\n"
        f"Severity: {ticket.get('severity') or 'unknown'}\n"
        f"Symptom: {ticket.get('description') or ticket['title']}"
    )


def _best_incident(evidence: list[EvidenceStep]) -> RelevantIncident | None:
    hits = [
        row
        for step in evidence
        if step.tool == "search_memory" and isinstance(step.returned, list)
        for row in step.returned
        if isinstance(row, dict) and "score" in row
    ]
    if not hits:
        return None
    best = min(hits, key=lambda row: row["score"])
    return RelevantIncident(
        id=best["id"], title=best.get("title", ""), score=best["score"]
    )


AgentEvent = tuple[str, EvidenceStep | HandleResponse]


def handle(ticket: dict) -> HandleResponse:
    *_, (_, result) = handle_events(ticket)
    return result


def handle_events(ticket: dict) -> Iterator[AgentEvent]:
    llm = get_llm()
    messages = [Message(role="user", text=_prompt(ticket))]
    evidence: list[EvidenceStep] = []
    diagnosis: Diagnosis | None = None

    def emit(use, returned, via: str, results: list[ToolResult]) -> EvidenceStep:
        step = EvidenceStep(tool=use.name, via=via, args=use.args, returned=returned)
        evidence.append(step)
        results.append(
            ToolResult(id=use.id, content=returned, is_error=via == "error")
        )
        return step

    for _ in range(settings.agent_max_turns):
        turn = llm.converse(SYSTEM, messages, TOOLS)
        if turn.truncated:
            log.warning(
                "The provider truncated the turn at max_tokens=%s: the tool_use may be missing",
                settings.max_tokens,
            )
        if not turn.tool_uses:
            messages.append(Message(role="assistant", text=turn.text or NO_CONTENT))
            messages.append(Message(role="user", text=DIAGNOSIS_REQUEST))
            continue

        messages.append(
            Message(role="assistant", text=turn.text or None, tool_uses=turn.tool_uses)
        )
        results: list[ToolResult] = []
        has_other_tools = any(
            use.name != SUBMIT_DIAGNOSIS.name for use in turn.tool_uses
        )
        for use in turn.tool_uses:
            if use.name == SUBMIT_DIAGNOSIS.name:
                if has_other_tools:
                    results.append(
                        ToolResult(
                            id=use.id,
                            content=PREMATURE_DIAGNOSIS,
                            is_error=True,
                        )
                    )
                    continue
                try:
                    diagnosis = Diagnosis.model_validate(use.args)
                except ValidationError as exc:
                    log.warning("submit_diagnosis with invalid arguments: %s", exc)
                    returned = {"error": str(exc)}
                    yield ("evidence", emit(use, returned, "error", results))
                continue
            try:
                returned, via = run_tool(use.name, use.args)
            except Exception as exc:
                log.exception("Tool %s failed", use.name)
                returned, via = {"error": str(exc)}, "error"
            yield ("evidence", emit(use, returned, via, results))

        if diagnosis is not None:
            break
        messages.append(Message(role="user", tool_results=results))

    cite_recalled(evidence)
    yield (
        "result",
        HandleResponse(
            ticket_id=ticket["id"],
            diagnosis=diagnosis or NO_DIAGNOSIS,
            most_relevant_incident=_best_incident(evidence),
            evidence=evidence,
        ),
    )
