import re

import pytest

from app.memory import FEEDBACK_COLUMNS, MEMORY_COLUMNS
from app.models import FeedbackResponse, Incident, Ticket
from app.tickets import TICKET_COLUMNS


def aliases(columns: str) -> set[str]:
    names = set()
    for part in columns.split(","):
        part = part.strip()
        match = re.search(r"AS\s+(\w+)$", part, re.IGNORECASE)
        names.add(match.group(1) if match else part)
    return names


def required_fields(model) -> set[str]:
    return {name for name, f in model.model_fields.items() if f.is_required()}


@pytest.mark.parametrize(
    "columns,model",
    [
        (TICKET_COLUMNS, Ticket),
        (MEMORY_COLUMNS, Incident),
        (FEEDBACK_COLUMNS, FeedbackResponse),
    ],
    ids=["Ticket", "Incident", "FeedbackResponse"],
)
def test_el_sql_devuelve_todo_lo_que_el_modelo_exige(columns, model):
    assert not required_fields(model) - aliases(columns)
