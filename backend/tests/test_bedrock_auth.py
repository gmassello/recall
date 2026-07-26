import os

from app.providers import bedrock
from app.providers.bedrock import (
    ACCESS_KEY_ENV,
    BEARER_TOKEN_ENV,
    SECRET_KEY_ENV,
    SESSION_TOKEN_ENV,
)


def _without_a_real_client(monkeypatch):
    monkeypatch.setattr(bedrock.boto3, "client", lambda *a, **kw: object())


def _without_credentials_in_the_environment(monkeypatch):
    for variable in (ACCESS_KEY_ENV, SECRET_KEY_ENV, SESSION_TOKEN_ENV):
        monkeypatch.delenv(variable, raising=False)


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


def test_the_credentials_from_the_env_file_reach_the_variables_boto3_reads(monkeypatch):
    _without_a_real_client(monkeypatch)
    _without_credentials_in_the_environment(monkeypatch)
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile", secret="secret-file")

    bedrock._client()

    assert os.environ[ACCESS_KEY_ENV] == "AKIAfile"
    assert os.environ[SECRET_KEY_ENV] == "secret-file"
    assert SESSION_TOKEN_ENV not in os.environ


def test_temporary_credentials_also_carry_the_session_token(monkeypatch):
    _without_a_real_client(monkeypatch)
    _without_credentials_in_the_environment(monkeypatch)
    _credentials_in_the_env_file(
        monkeypatch, key="ASIAfile", secret="secret-file", token="token-file"
    )

    bedrock._client()

    assert os.environ[SESSION_TOKEN_ENV] == "token-file"


def test_the_credentials_in_the_environment_beat_the_env_file(monkeypatch):
    _without_a_real_client(monkeypatch)
    _without_credentials_in_the_environment(monkeypatch)
    monkeypatch.setenv(ACCESS_KEY_ENV, "AKIAshell")
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile", secret="secret-file")

    bedrock._client()

    assert os.environ[ACCESS_KEY_ENV] == "AKIAshell"


def test_half_a_credential_pair_leaves_the_environment_alone(monkeypatch):
    _without_a_real_client(monkeypatch)
    _without_credentials_in_the_environment(monkeypatch)
    _credentials_in_the_env_file(monkeypatch, key="AKIAfile")

    bedrock._client()

    assert ACCESS_KEY_ENV not in os.environ
    assert SECRET_KEY_ENV not in os.environ
