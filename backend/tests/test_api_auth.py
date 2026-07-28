import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api import incidents, memory, tickets
from app.api.deps import require_api_key
from app.config import settings

DESTRUCTIVE_METHODS = {"DELETE", "PATCH"}
ROUTERS = [tickets.router, incidents.router, memory.router]


@pytest.fixture
def demo_key(monkeypatch):
    monkeypatch.setattr(settings, "demo_api_key", "s3cret")
    return "s3cret"


def test_without_a_configured_key_every_request_passes(monkeypatch):
    monkeypatch.setattr(settings, "demo_api_key", "")

    assert require_api_key("") is None


def test_the_right_key_passes(demo_key):
    assert require_api_key(demo_key) is None


@pytest.mark.parametrize("header", ["", "wrong", "s3cre", "s3cret "])
def test_a_missing_or_wrong_key_is_rejected(demo_key, header):
    with pytest.raises(HTTPException) as raised:
        require_api_key(header)

    assert raised.value.status_code == 401


def test_every_destructive_route_is_protected():
    destructive = [
        (method, route)
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods & DESTRUCTIVE_METHODS
    ]
    unprotected = [
        f"{method} {route.path}"
        for method, route in destructive
        if require_api_key not in [d.call for d in route.dependant.dependencies]
    ]

    assert len(destructive) >= 5
    assert unprotected == []
