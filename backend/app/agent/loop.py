import logging

from pydantic import ValidationError

from app.agent.tools import SUBMIT_DIAGNOSIS, TOOLS, run_tool
from app.config import settings
from app.models import Diagnosis, EvidenceStep, HandleResponse, RelevantIncident
from app.providers.base import Message, ToolResult
from app.providers.registry import get_llm

log = logging.getLogger(__name__)

SYSTEM = """Sos un ingeniero de guardia. Recibis un ticket de incidente y tenes que
diagnosticarlo apoyandote en la memoria de incidentes pasados.

Procedimiento:
1. Usa search_memory con el sintoma del ticket. Es tu fuente principal.
2. Si necesitas contexto operativo del servicio, usa query_incidents.
3. Terminas SIEMPRE llamando a submit_diagnosis.

Regla que no se rompe: si la memoria no devolvio nada parecido, decilo en root_cause
y poné una confidence baja. Un "no tengo antecedentes de esto" es una respuesta
correcta; una causa raiz inventada no lo es."""

NO_DIAGNOSIS = Diagnosis(
    root_cause="El agente no llego a un diagnostico dentro del limite de turnos.",
    mitigation_steps=["Revisar manualmente el ticket."],
    confidence=0.0,
)


def _prompt(ticket: dict) -> str:
    return (
        f"Ticket: {ticket['title']}\n"
        f"Servicio: {ticket.get('service') or 'desconocido'}\n"
        f"Severidad: {ticket.get('severity') or 'desconocida'}\n"
        f"Sintoma: {ticket.get('description') or ticket['title']}"
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


def handle(ticket: dict) -> HandleResponse:
    llm = get_llm()
    messages = [Message(role="user", text=_prompt(ticket))]
    evidence: list[EvidenceStep] = []
    diagnosis: Diagnosis | None = None

    for _ in range(settings.agent_max_turns):
        turn = llm.converse(SYSTEM, messages, TOOLS)
        if not turn.tool_uses:
            break

        messages.append(
            Message(role="assistant", text=turn.text or None, tool_uses=turn.tool_uses)
        )
        results: list[ToolResult] = []
        for use in turn.tool_uses:
            if use.name == SUBMIT_DIAGNOSIS.name:
                try:
                    diagnosis = Diagnosis.model_validate(use.args)
                except ValidationError as exc:
                    log.warning("submit_diagnosis con argumentos invalidos: %s", exc)
                    returned = {"error": str(exc)}
                    evidence.append(
                        EvidenceStep(
                            tool=use.name, via="error", args=use.args, returned=returned
                        )
                    )
                    results.append(ToolResult(id=use.id, content=returned))
                continue
            try:
                returned, via = run_tool(use.name, use.args)
            except Exception as exc:
                log.exception("Fallo la herramienta %s", use.name)
                returned, via = {"error": str(exc)}, "error"
            evidence.append(
                EvidenceStep(tool=use.name, via=via, args=use.args, returned=returned)
            )
            results.append(ToolResult(id=use.id, content=returned))

        if diagnosis is not None:
            break
        messages.append(Message(role="user", tool_results=results))

    return HandleResponse(
        ticket_id=ticket["id"],
        diagnosis=diagnosis or NO_DIAGNOSIS,
        most_relevant_incident=_best_incident(evidence),
        evidence=evidence,
    )
