import pytest

from app.agent import loop, tools
from app.config import settings
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
def citas(monkeypatch):
    registradas: list[list[str]] = []
    monkeypatch.setattr(tools.memory, "cite", lambda ids: registradas.append(list(ids)))
    return registradas


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


def test_no_diagnostica_en_el_mismo_turno_que_busca(fake_llm, monkeypatch, citas):
    monkeypatch.setattr(loop, "run_tool", lambda name, args: ([{"id": "i1"}], "mcp"))
    turno_mezclado = Turn(
        tool_uses=[
            ToolUse(id="busca", name="search_memory", args={"symptom": "x"}),
            ToolUse(id="diagnostica", name="submit_diagnosis", args=VALIDO),
        ]
    )
    llm = fake_llm([turno_mezclado, submit(VALIDO, use_id="tarde")])

    respuesta = loop.handle(TICKET)

    postergados = [
        result
        for message in llm.calls[1]
        for result in message.tool_results
        if result.id == "diagnostica"
    ]
    assert postergados, "el submit_diagnosis prematuro no recibio su tool_result"
    assert "descarto" in str(postergados[0].content)

    assert respuesta.diagnosis.root_cause == "Pool de conexiones agotado"
    assert [step.tool for step in respuesta.evidence] == ["search_memory"]


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


def busca(use_id: str) -> Turn:
    return Turn(tool_uses=[ToolUse(id=use_id, name="search_memory", args={"symptom": "x"})])


def test_cita_una_sola_vez_por_diagnostico_sin_repetir_ids(fake_llm, monkeypatch, citas):
    monkeypatch.setattr(
        loop, "run_tool", lambda name, args: ([{"id": "i1"}, {"id": "i2"}], "mcp")
    )
    fake_llm([busca("b1"), busca("b2"), submit(VALIDO)])

    loop.handle(TICKET)

    assert citas == [["i1", "i2"]]


def test_sin_memoria_recuperada_no_cita(fake_llm, citas):
    fake_llm([submit(VALIDO)])

    loop.handle(TICKET)

    assert citas == [[]]


def test_turno_de_solo_texto_pide_el_diagnostico_en_vez_de_cortar(fake_llm, citas):
    llm = fake_llm([Turn(text="Estoy pensando."), submit(VALIDO)])

    respuesta = loop.handle(TICKET)

    assert respuesta.diagnosis.root_cause == "Pool de conexiones agotado"
    textos = [m.text for m in llm.calls[1] if m.text]
    assert loop.PEDIDO_DE_DIAGNOSTICO in textos


def test_solo_texto_hasta_agotar_turnos_si_da_no_diagnosis(fake_llm, citas):
    llm = fake_llm([Turn(text="Sigo pensando.")])

    respuesta = loop.handle(TICKET)

    assert respuesta.diagnosis == loop.NO_DIAGNOSIS
    assert len(llm.calls) == settings.agent_max_turns


def test_los_resultados_de_error_viajan_marcados(fake_llm, monkeypatch, citas):
    def explota(name, args):
        raise RuntimeError("la tool fallo")

    monkeypatch.setattr(loop, "run_tool", explota)
    llm = fake_llm([busca("b1"), submit(VALIDO)])

    loop.handle(TICKET)

    marcados = [
        r for m in llm.calls[1] for r in m.tool_results if r.id == "b1"
    ]
    assert marcados and marcados[0].is_error is True
