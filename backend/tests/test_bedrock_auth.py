import os

from app.providers import bedrock
from app.providers.bedrock import BEARER_TOKEN_ENV


def _without_a_real_client(monkeypatch):
    monkeypatch.setattr(bedrock.boto3, "client", lambda *a, **kw: object())


def _capturing_the_client(monkeypatch):
    captured: dict = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(bedrock.boto3, "client", fake_client)
    return captured


def _credentials_in_the_env_file(monkeypatch, key="", secret="", token=""):
    monkeypatch.setattr(bedrock.settings, "aws_access_key_id", key)
    monkeypatch.setattr(bedrock.settings, "aws_secret_access_key", secret)
    monkeypatch.setattr(bedrock.settings, "aws_session_token", token)


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


def test_the_credentials_from_the_env_file_reach_the_client_explicitly(monkeypatch):
    captured = _capturing_the_client(monkeypatch)
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile", secret="secret-file")

    bedrock._client()

    assert captured["aws_access_key_id"] == "AKIAfile"
    assert captured["aws_secret_access_key"] == "secret-file"
    assert "aws_session_token" not in captured


def test_temporary_credentials_also_carry_the_session_token(monkeypatch):
    captured = _capturing_the_client(monkeypatch)
    _credentials_in_the_env_file(
        monkeypatch, key="ASIAfile", secret="secret-file", token="token-file"
    )

    bedrock._client()

    assert captured["aws_session_token"] == "token-file"


def test_the_env_file_credentials_beat_the_ambient_environment(monkeypatch):
    captured = _capturing_the_client(monkeypatch)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAshell")
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile", secret="secret-file")

    bedrock._client()

    assert captured["aws_access_key_id"] == "AKIAfile"


def test_half_a_credential_pair_is_not_sent(monkeypatch):
    captured = _capturing_the_client(monkeypatch)
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile")

    bedrock._client()

    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured
