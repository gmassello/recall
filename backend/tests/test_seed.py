import pytest

from seed import seed_memory


class FakeSource:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.ingested: list[str] = []
        self.states: list[str] = []

    def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        return self.existing & set(external_ids)

    def ingest(self, ticket) -> dict:
        self.ingested.append(ticket.external_id)
        return {"id": f"id-{ticket.external_id}"}

    def set_status(self, ticket_id: str, status: str) -> None:
        self.states.append(status)


@pytest.fixture
def source(monkeypatch):
    def with_existing(existing: set[str]) -> FakeSource:
        fake = FakeSource(existing)
        monkeypatch.setattr(seed_memory.tickets, "source", fake)
        return fake

    return with_existing


def test_a_fresh_seed_ingests_every_ticket_with_its_status(source):
    fake = source(set())

    seed_memory.seed_tickets()

    assert len(fake.ingested) > 0
    assert len(fake.states) == len(fake.ingested)


def test_reseeding_does_not_touch_existing_tickets(source):
    first = source(set())
    seed_memory.seed_tickets()

    rerun = source(set(first.ingested))
    seed_memory.seed_tickets()

    assert rerun.ingested == []
    assert rerun.states == []
