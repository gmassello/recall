import pytest

from app.agent import loop, tools
from app.config import settings
from app.providers.base import ToolUse, Turn

TICKET = {
    "id": "ticket-1",
    "title": "[payments-api] slow checkout",
    "description": "p99 latency at 4200ms",
    "service": "payments-api",
    "severity": "sev2",
}

VALID = {
    "root_cause": "Connection pool exhausted",
    "mitigation_steps": ["Raise max_connections"],
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
def citations(monkeypatch):
    recorded: list[list[str]] = []
    monkeypatch.setattr(tools.memory, "cite", lambda ids: recorded.append(list(ids)))
    return recorded


@pytest.fixture
def fake_llm(monkeypatch):
    def _install(turns: list[Turn]) -> FakeLLM:
        llm = FakeLLM(turns)
        monkeypatch.setattr(loop, "get_llm", lambda: llm)
        return llm

    return _install


def test_valid_diagnosis_on_first_attempt(fake_llm):
    fake_llm([submit(VALID)])

    response = loop.handle(TICKET)

    assert response.diagnosis.root_cause == "Connection pool exhausted"
    assert response.diagnosis.confidence == 0.8


@pytest.mark.parametrize(
    "invalid_args",
    [
        {"root_cause": 123},
        {"confidence": "high"},
        {"mitigation_steps": "not a list"},
        {},
    ],
    ids=["root_cause-numeric", "confidence-string", "steps-not-a-list", "empty"],
)
def test_invalid_arguments_do_not_propagate_an_exception(fake_llm, invalid_args):
    fake_llm([submit(invalid_args)])

    response = loop.handle(TICKET)

    assert response.diagnosis == loop.NO_DIAGNOSIS
    assert [step.via for step in response.evidence] == ["error"] * len(
        response.evidence
    )
    assert response.evidence, "the failed attempt did not land in the evidence"


def test_does_not_diagnose_in_the_same_turn_it_searches(fake_llm, monkeypatch, citations):
    monkeypatch.setattr(loop, "run_tool", lambda name, args: ([{"id": "i1"}], "mcp"))
    mixed_turn = Turn(
        tool_uses=[
            ToolUse(id="search", name="search_memory", args={"symptom": "x"}),
            ToolUse(id="diagnose", name="submit_diagnosis", args=VALID),
        ]
    )
    llm = fake_llm([mixed_turn, submit(VALID, use_id="late")])

    response = loop.handle(TICKET)

    deferred = [
        result
        for message in llm.calls[1]
        for result in message.tool_results
        if result.id == "diagnose"
    ]
    assert deferred, "the premature submit_diagnosis did not get its tool_result"
    assert deferred[0].content == loop.PREMATURE_DIAGNOSIS

    assert response.diagnosis.root_cause == "Connection pool exhausted"
    assert [step.tool for step in response.evidence] == ["search_memory"]


def test_the_model_receives_the_error_and_corrects_itself(fake_llm):
    llm = fake_llm([submit({"root_cause": 123}), submit(VALID, use_id="use-2")])

    response = loop.handle(TICKET)

    assert response.diagnosis.root_cause == "Connection pool exhausted"

    second_call = llm.calls[1]
    errors = [
        result
        for message in second_call
        for result in message.tool_results
        if "error" in str(result.content)
    ]
    assert errors, "the validation error did not go back to the model as a tool_result"
    assert errors[0].id == "use-1"


def search(use_id: str) -> Turn:
    return Turn(tool_uses=[ToolUse(id=use_id, name="search_memory", args={"symptom": "x"})])


def test_cites_once_per_diagnosis_without_repeating_ids(fake_llm, monkeypatch, citations):
    monkeypatch.setattr(
        loop, "run_tool", lambda name, args: ([{"id": "i1"}, {"id": "i2"}], "mcp")
    )
    fake_llm([search("b1"), search("b2"), submit(VALID)])

    loop.handle(TICKET)

    assert citations == [["i1", "i2"]]


def test_without_recalled_memory_it_does_not_cite(fake_llm, citations):
    fake_llm([submit(VALID)])

    loop.handle(TICKET)

    assert citations == [[]]


def test_a_text_only_turn_asks_for_the_diagnosis_instead_of_stopping(fake_llm, citations):
    llm = fake_llm([Turn(text="I am thinking."), submit(VALID)])

    response = loop.handle(TICKET)

    assert response.diagnosis.root_cause == "Connection pool exhausted"
    texts = [m.text for m in llm.calls[1] if m.text]
    assert loop.DIAGNOSIS_REQUEST in texts


def test_text_only_until_turns_run_out_gives_no_diagnosis(fake_llm, citations):
    llm = fake_llm([Turn(text="Still thinking.")])

    response = loop.handle(TICKET)

    assert response.diagnosis == loop.NO_DIAGNOSIS
    assert len(llm.calls) == settings.agent_max_turns


def test_error_results_are_marked_is_error(fake_llm, monkeypatch, citations):
    def raises(name, args):
        raise RuntimeError("the tool failed")

    monkeypatch.setattr(loop, "run_tool", raises)
    llm = fake_llm([search("b1"), submit(VALID)])

    loop.handle(TICKET)

    flagged = [
        r for m in llm.calls[1] for r in m.tool_results if r.id == "b1"
    ]
    assert flagged and flagged[0].is_error is True
