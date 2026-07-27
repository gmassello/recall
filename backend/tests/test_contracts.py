import re

import pytest

from app.config import settings
from app.memory import FEEDBACK_COLUMNS, MEMORY_COLUMNS, VECTOR_CAST, _recall_sql
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
def test_the_sql_returns_everything_the_model_requires(columns, model):
    assert not required_fields(model) - aliases(columns)


def test_the_vector_cast_carries_the_dimension_from_the_config():
    assert VECTOR_CAST == f"::VECTOR({settings.embedding_dims})"


def test_the_recall_sql_casts_with_the_dimension():
    sql, _ = _recall_sql([0.1] * settings.embedding_dims, None)

    assert VECTOR_CAST in sql
    assert "%s::VECTOR " not in sql
    assert not sql.rstrip().endswith("%s::VECTOR")
