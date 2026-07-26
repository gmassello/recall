import os

from app.providers import bedrock
from app.providers.bedrock import BEARER_TOKEN_ENV


def _without_a_real_client(monkeypatch):
    monkeypatch.setattr(bedrock.boto3, "client", lambda *a, **kw: object())


def test_the_key_from_the_env_file_propagates_to_the_variable_boto3_reads(monkeypatch):
    _without_a_real_client(monkeypatch)
    monkeypatch.delenv(BEARER_TOKEN_ENV, raising=False)
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "ABSKfrom-env-file")

    bedrock._client()

    assert os.environ[BEARER_TOKEN_ENV] == "ABSKfrom-env-file"


def test_the_environment_variable_beats_the_env_file(monkeypatch):
    _without_a_real_client(monkeypatch)
    monkeypatch.setenv(BEARER_TOKEN_ENV, "ABSKfrom-the-shell")
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "ABSKfrom-env-file")

    bedrock._client()

    assert os.environ[BEARER_TOKEN_ENV] == "ABSKfrom-the-shell"


def test_without_a_configured_key_the_environment_is_left_alone(monkeypatch):
    _without_a_real_client(monkeypatch)
    monkeypatch.delenv(BEARER_TOKEN_ENV, raising=False)
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "")

    bedrock._client()

    assert BEARER_TOKEN_ENV not in os.environ
