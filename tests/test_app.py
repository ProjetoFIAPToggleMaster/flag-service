"""
Testes do flag-service.

Observação importante: o `app.py` abre um pool de conexão com o PostgreSQL
já no momento do import (e faz sys.exit se as variáveis de ambiente faltarem).
Por isso o CI sobe um container Postgres e define DATABASE_URL / AUTH_SERVICE_URL
antes de rodar o pytest. As chamadas ao auth-service são "mockadas" para não
depender de um serviço externo.
"""
from unittest.mock import patch, MagicMock

import pytest

# Importado no nível do módulo: exige env vars + Postgres acessível (providos pelo CI).
import app as flag_app


@pytest.fixture
def client():
    flag_app.app.config.update({"TESTING": True})
    with flag_app.app.test_client() as c:
        yield c


def _auth_response(status_code):
    """Cria uma resposta falsa do auth-service com o status desejado."""
    mock = MagicMock()
    mock.status_code = status_code
    return mock


def test_health_ok(client):
    """/health não exige autenticação nem banco."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_flags_requires_auth_header(client):
    """Sem header Authorization deve retornar 401."""
    resp = client.get("/flags")
    assert resp.status_code == 401


def test_invalid_api_key_returns_401(client):
    """Se o auth-service reprovar a chave, o endpoint deve retornar 401."""
    with patch("app.requests.get", return_value=_auth_response(401)):
        resp = client.get("/flags", headers={"Authorization": "Bearer chave-invalida"})
    assert resp.status_code == 401


def test_create_and_list_flag(client):
    """Fluxo feliz: cria uma flag e confirma que ela aparece na listagem."""
    flag_name = "ci-test-flag"
    headers = {"Authorization": "Bearer chave-valida", "Content-Type": "application/json"}

    with patch("app.requests.get", return_value=_auth_response(200)):
        # Garante estado limpo (ignora 404 se não existir).
        client.delete(f"/flags/{flag_name}", headers=headers)

        create = client.post(
            "/flags",
            headers=headers,
            json={"name": flag_name, "description": "criada pelo CI", "is_enabled": True},
        )
        # 201 na criação; 409 se por acaso já existir (mantém o teste idempotente).
        assert create.status_code in (201, 409)

        listing = client.get("/flags", headers=headers)
        assert listing.status_code == 200
        names = [flag["name"] for flag in listing.get_json()]
        assert flag_name in names


def test_create_flag_without_name_returns_400(client):
    """Payload sem 'name' deve ser rejeitado com 400."""
    headers = {"Authorization": "Bearer chave-valida", "Content-Type": "application/json"}
    with patch("app.requests.get", return_value=_auth_response(200)):
        resp = client.post("/flags", headers=headers, json={"description": "sem nome"})
    assert resp.status_code == 400
