import pytest

from app.agent import loop
from app.providers.base import ToolUse, Turn

TICKET = {
    "id": "ticket-1",
    "title": "[payments-api] checkout lento",
    "description": "latencia p99 en 4200ms",
    "service": "payments-api",
    "severity": "sev2",
}

VALIDO = {
    "root_cause": "Pool de conexiones agotado",
    "mitigation_steps": ["Subir max_connections"],
    "confidence": 0.8,
}


def submit(args: dict, use_id: str = "use-1") -> Turn:
    return Turn(tool_uses=[ToolUse(id=use_id, name="submit_diagnosis", args=args)])


class FakeLLM:
    def __init__(self, turns: list[Turn]) -> None:
        self.turns = turns
        self.calls: list[list] = []

    def converse(self, system, messages, tools) -> Turn:
        self.calls.append(list(messages))
        return self.turns[min(len(self.calls) - 1, len(self.turns) - 1)]


@pytest.fixture
def fake_llm(monkeypatch):
    def _install(turns: list[Turn]) -> FakeLLM:
        llm = FakeLLM(turns)
        monkeypatch.setattr(loop, "get_llm", lambda: llm)
        return llm

    return _install


def test_diagnostico_valido_al_primer_intento(fake_llm):
    fake_llm([submit(VALIDO)])

    respuesta = loop.handle(TICKET)

    assert respuesta.diagnosis.root_cause == "Pool de conexiones agotado"
    assert respuesta.diagnosis.confidence == 0.8


@pytest.mark.parametrize(
    "args_invalidos",
    [
        {"root_cause": 123},
        {"confidence": "alta"},
        {"mitigation_steps": "no es una lista"},
        {},
    ],
    ids=["root_cause-numerico", "confidence-string", "steps-no-lista", "vacio"],
)
def test_argumentos_invalidos_no_propagan_excepcion(fake_llm, args_invalidos):
    fake_llm([submit(args_invalidos)])

    respuesta = loop.handle(TICKET)

    assert respuesta.diagnosis == loop.NO_DIAGNOSIS
    assert [step.via for step in respuesta.evidence] == ["error"] * len(
        respuesta.evidence
    )
    assert respuesta.evidence, "el intento fallido no quedo en la evidencia"


def test_el_modelo_recibe_el_error_y_se_corrige(fake_llm):
    llm = fake_llm([submit({"root_cause": 123}), submit(VALIDO, use_id="use-2")])

    respuesta = loop.handle(TICKET)

    assert respuesta.diagnosis.root_cause == "Pool de conexiones agotado"

    segunda_llamada = llm.calls[1]
    errores = [
        result
        for message in segunda_llamada
        for result in message.tool_results
        if "error" in str(result.content)
    ]
    assert errores, "el error de validacion no volvio al modelo como tool_result"
    assert errores[0].id == "use-1"
