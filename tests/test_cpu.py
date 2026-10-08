from pathlib import Path
import runpy

import pytest
from fastapi.testclient import TestClient

from apps.cpu_bound.main import LIMITE_MAXIMO, app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("limite", "quantidade"),
    [(1, 0), (2, 1), (3, 2), (4, 2), (9, 4), (10, 4), (25, 9), (100, 25), (1000, 168)],
)
def test_primos_conhecidos(client, limite, quantidade):
    response = client.get("/primos", params={"limite": limite})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "tipo": "CPU-bound",
        "limite": limite,
        "quantidade_primos": quantidade,
    }
    assert type(response.json()["limite"]) is int
    assert type(response.json()["quantidade_primos"]) is int


@pytest.mark.parametrize("limite", ["0", "-1", "abc", "1.5", "", str(LIMITE_MAXIMO + 1)])
def test_parametros_invalidos(client, limite):
    response = client.get("/primos", params={"limite": limite})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    assert isinstance(response.json()["detail"], list)
    assert response.json()["detail"][0]["loc"] == ["query", "limite"]


def test_limite_padrao(client):
    response = client.get("/primos")

    assert response.status_code == 200
    assert response.json() == {
        "tipo": "CPU-bound",
        "limite": 100000,
        "quantidade_primos": 9592,
    }


def test_resultado_deterministico(client):
    primeira = client.get("/primos", params={"limite": 100})
    segunda = client.get("/primos", params={"limite": 100})

    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json() == segunda.json()


def test_limite_configuravel(monkeypatch):
    monkeypatch.setenv("CPU_LIMITE_MAX", "29")
    modulo = runpy.run_path(str(Path(__file__).parents[1] / "apps/cpu_bound/main.py"))

    with TestClient(modulo["app"]) as client:
        response = client.get("/primos", params={"limite": 29})
        assert response.status_code == 200
        assert response.json() == {
            "tipo": "CPU-bound",
            "limite": 29,
            "quantidade_primos": 10,
        }
        assert client.get("/primos", params={"limite": 30}).status_code == 422
        assert client.get("/primos").json() == response.json()


@pytest.mark.parametrize("valor", ["0", "-1", "abc"])
def test_configuracao_invalida(monkeypatch, valor):
    monkeypatch.setenv("CPU_LIMITE_MAX", valor)

    with pytest.raises(ValueError):
        runpy.run_path(str(Path(__file__).parents[1] / "apps/cpu_bound/main.py"))
