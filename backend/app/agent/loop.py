import logging
from collections.abc import Iterator

from pydantic import ValidationError

from app.agent.tools import SUBMIT_DIAGNOSIS, TOOLS, cite_recalled, run_tool
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

SIN_RESPUESTA = "(sin contenido)"

PEDIDO_DE_DIAGNOSTICO = (
    "No llamaste a ninguna herramienta. Si ya tenes lo necesario, llama a "
    "submit_diagnosis; si te falta contexto, usa search_memory o query_incidents."
)

DIAGNOSTICO_PREMATURO = {
    "error": (
        "Llamaste a submit_diagnosis en el mismo turno que otras herramientas, "
        "asi que todavia no viste lo que devolvieron. Se descarto el diagnostico. "
        "Revisa los resultados de este turno y volve a llamar a submit_diagnosis."
    )
}

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


AgentEvent = tuple[str, EvidenceStep | HandleResponse]


def handle(ticket: dict) -> HandleResponse:
    *_, (_, result) = handle_events(ticket)
    return result


def handle_events(ticket: dict) -> Iterator[AgentEvent]:
    llm = get_llm()
    messages = [Message(role="user", text=_prompt(ticket))]
    evidence: list[EvidenceStep] = []
    diagnosis: Diagnosis | None = None

    def emitir(use, returned, via: str, results: list[ToolResult]) -> EvidenceStep:
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
                "El proveedor trunco el turno en max_tokens=%s: el tool_use puede faltar",
                settings.max_tokens,
            )
        if not turn.tool_uses:
            messages.append(
                Message(role="assistant", text=turn.text or SIN_RESPUESTA)
            )
            messages.append(Message(role="user", text=PEDIDO_DE_DIAGNOSTICO))
            continue

        messages.append(
            Message(role="assistant", text=turn.text or None, tool_uses=turn.tool_uses)
        )
        results: list[ToolResult] = []
        hay_otras_tools = any(
            use.name != SUBMIT_DIAGNOSIS.name for use in turn.tool_uses
        )
        for use in turn.tool_uses:
            if use.name == SUBMIT_DIAGNOSIS.name:
                if hay_otras_tools:
                    results.append(
                        ToolResult(
                            id=use.id,
                            content=DIAGNOSTICO_PREMATURO,
                            is_error=True,
                        )
                    )
                    continue
                try:
                    diagnosis = Diagnosis.model_validate(use.args)
                except ValidationError as exc:
                    log.warning("submit_diagnosis con argumentos invalidos: %s", exc)
                    returned = {"error": str(exc)}
                    yield ("evidence", emitir(use, returned, "error", results))
                continue
            try:
                returned, via = run_tool(use.name, use.args)
            except Exception as exc:
                log.exception("Fallo la herramienta %s", use.name)
                returned, via = {"error": str(exc)}, "error"
            yield ("evidence", emitir(use, returned, via, results))

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
