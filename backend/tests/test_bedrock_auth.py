import os

from app.providers import bedrock
from app.providers.bedrock import BEARER_TOKEN_ENV


def _sin_cliente_real(monkeypatch):
    monkeypatch.setattr(bedrock.boto3, "client", lambda *a, **kw: object())


def test_la_key_del_env_file_se_propaga_a_la_variable_que_lee_boto3(monkeypatch):
    _sin_cliente_real(monkeypatch)
    monkeypatch.delenv(BEARER_TOKEN_ENV, raising=False)
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "ABSKdesde-env-file")

    bedrock._client()

    assert os.environ[BEARER_TOKEN_ENV] == "ABSKdesde-env-file"


def test_la_variable_del_entorno_le_gana_al_env_file(monkeypatch):
    _sin_cliente_real(monkeypatch)
    monkeypatch.setenv(BEARER_TOKEN_ENV, "ABSKdesde-el-shell")
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "ABSKdesde-env-file")

    bedrock._client()

    assert os.environ[BEARER_TOKEN_ENV] == "ABSKdesde-el-shell"


def test_sin_key_configurada_no_se_toca_el_entorno(monkeypatch):
    _sin_cliente_real(monkeypatch)
    monkeypatch.delenv(BEARER_TOKEN_ENV, raising=False)
    monkeypatch.setattr(bedrock.settings, "bedrock_api_key", "")

    bedrock._client()

    assert BEARER_TOKEN_ENV not in os.environ
