from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import runpy
from threading import BoundedSemaphore, Event, Lock

import pytest
from fastapi.testclient import TestClient

from apps.memory_bound import main


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def verificacao_esperada(tamanho_mb):
    tamanho_bytes = tamanho_mb * 1024 * 1024
    return (tamanho_bytes + main.PAGESIZE - 1) // main.PAGESIZE + 1


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("tamanho_mb", [1, 2, 10, 50, 64])
def test_tamanhos_e_formato_json(client, tamanho_mb):
    response = client.get("/memoria", params={"tamanho_mb": tamanho_mb})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "tipo": "Memory-bound",
        "tamanho_mb": tamanho_mb,
        "verificacao": verificacao_esperada(tamanho_mb),
    }
    assert type(response.json()["tamanho_mb"]) is int
    assert type(response.json()["verificacao"]) is int


def test_tamanho_padrao(client):
    response = client.get("/memoria")
    assert response.status_code == 200
    assert response.json() == {
        "tipo": "Memory-bound", "tamanho_mb": 50, "verificacao": verificacao_esperada(50)
    }


@pytest.mark.parametrize("valor", ["0", "-1", "65", "abc", "1.5", ""])
def test_parametros_invalidos_sem_alocar(client, monkeypatch, valor):
    def alocacao_proibida(tamanho):
        pytest.fail("Uma entrada inválida não deve alocar memória.")

    monkeypatch.setattr(main, "alocar_memoria", alocacao_proibida)
    response = client.get("/memoria", params={"tamanho_mb": valor})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    assert isinstance(response.json()["detail"], list)
    assert response.json()["detail"][0]["loc"] == ["query", "tamanho_mb"]


def test_escrita_e_leitura_por_pagina():
    with main.alocar_memoria(2 * main.PAGESIZE + 17) as dados:
        assert main.escrever_e_verificar(dados) == 4
        assert [dados[0], dados[main.PAGESIZE], dados[2 * main.PAGESIZE], dados[-1]] == [1] * 4
        assert dados[1] == 0
        assert main.escrever_e_verificar(dados) == 4
    assert dados.closed


@pytest.fixture
def buffers_rastreados(monkeypatch):
    buffers = []
    alocador_original = main.alocar_memoria

    def alocar(tamanho):
        buffer = alocador_original(tamanho)
        buffers.append(buffer)
        return buffer

    monkeypatch.setattr(main, "alocar_memoria", alocar)
    # Mantém os objetos para conferir o fechamento explícito, sem depender do GC.
    return buffers


def test_liberacao_apos_requisicoes(client, buffers_rastreados, monkeypatch):
    def retencao_proibida(segundos):
        pytest.fail("A retenção padrão deve estar desativada.")

    monkeypatch.setattr(main, "sleep", retencao_proibida)
    for _ in range(5):
        assert client.get("/memoria", params={"tamanho_mb": 2}).status_code == 200
        assert all(buffer.closed for buffer in buffers_rastreados)
    assert len(buffers_rastreados) == 5


def test_retencao_apos_verificacao(client, buffers_rastreados, monkeypatch):
    monkeypatch.setattr(main, "RETENCAO_SEGUNDOS", 0.25)
    chamadas = []

    def observar(segundos):
        dados = buffers_rastreados[0]
        assert not dados.closed
        assert len(dados) == 1024 * 1024
        assert dados[0] == dados[-1] == 1
        chamadas.append(segundos)

    monkeypatch.setattr(main, "sleep", observar)
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 200
    assert chamadas == [0.25]
    assert buffers_rastreados[0].closed


def test_concorrencia_sobreposicao_e_limite(client, buffers_rastreados, monkeypatch):
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(2))
    monkeypatch.setattr(main, "RETENCAO_SEGUNDOS", 1)
    duas_retidas = Event()
    liberar = Event()
    lock = Lock()
    entradas = 0

    def reter(segundos):
        nonlocal entradas
        with lock:
            entradas += 1
            if entradas == 2:
                duas_retidas.set()
        if not liberar.wait(timeout=10):
            raise RuntimeError("O teste não liberou as requisições retidas.")

    monkeypatch.setattr(main, "sleep", reter)
    with ThreadPoolExecutor(max_workers=3) as executor:
        respostas = [
            executor.submit(client.get, "/memoria", params={"tamanho_mb": 1})
            for _ in range(2)
        ]
        try:
            assert duas_retidas.wait(timeout=5), "As duas alocações devem se sobrepor."
            assert len(buffers_rastreados) == 2
            assert all(not buffer.closed for buffer in buffers_rastreados)
            # Estes pedidos devem terminar enquanto os dois buffers estão retidos.
            health = executor.submit(client.get, "/health").result(timeout=5)
            assert health.status_code == 200
            excesso = executor.submit(client.get, "/memoria", params={"tamanho_mb": 1}).result(timeout=5)
            assert excesso.status_code == 503
            assert len(buffers_rastreados) == 2
        finally:
            liberar.set()
        assert all(future.result(timeout=5).status_code == 200 for future in respostas)
    assert all(buffer.closed for buffer in buffers_rastreados)
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 200


@pytest.mark.parametrize("erro", [MemoryError, OSError])
def test_falha_na_alocacao_devolve_vaga(client, monkeypatch, erro):
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))
    chamadas = 0
    alocador_original = main.alocar_memoria

    def alocar(tamanho):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            raise erro
        return alocador_original(tamanho)

    monkeypatch.setattr(main, "alocar_memoria", alocar)
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 503
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 200


def test_falha_na_retencao_libera_buffer_e_vaga(client, buffers_rastreados, monkeypatch):
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))
    monkeypatch.setattr(main, "RETENCAO_SEGUNDOS", 1)

    def falhar(segundos):
        raise RuntimeError("Falha simulada na retenção.")

    monkeypatch.setattr(main, "sleep", falhar)
    with TestClient(main.app, raise_server_exceptions=False) as cliente_com_erro:
        assert cliente_com_erro.get("/memoria", params={"tamanho_mb": 1}).status_code == 500
    assert buffers_rastreados[0].closed
    monkeypatch.setattr(main, "RETENCAO_SEGUNDOS", 0)
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 200


def test_falha_na_verificacao_fecha_mapeamento(client, buffers_rastreados, monkeypatch):
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))
    verificar_original = main.escrever_e_verificar

    def falhar(dados):
        raise RuntimeError("Falha simulada na verificação.")

    monkeypatch.setattr(main, "escrever_e_verificar", falhar)
    with TestClient(main.app, raise_server_exceptions=False) as cliente_com_erro:
        assert cliente_com_erro.get("/memoria", params={"tamanho_mb": 1}).status_code == 500
    assert buffers_rastreados[0].closed
    with pytest.raises(ValueError):
        _ = buffers_rastreados[0][0]
    monkeypatch.setattr(main, "escrever_e_verificar", verificar_original)
    assert client.get("/memoria", params={"tamanho_mb": 1}).status_code == 200


def carregar_configuracao():
    return runpy.run_path(str(Path(__file__).parents[1] / "apps/memory_bound/main.py"))


@pytest.mark.parametrize(("minimo", "maximo", "padrao"), [(2, 3, 3), (51, 52, 51)])
def test_limites_configuraveis(monkeypatch, minimo, maximo, padrao):
    monkeypatch.setenv("MEMORY_LIMITE_MIN_MB", str(minimo))
    monkeypatch.setenv("MEMORY_LIMITE_MAX_MB", str(maximo))
    monkeypatch.setenv("MEMORY_MAX_SIMULTANEAS", "2")
    monkeypatch.setenv("MEMORY_RETENCAO_SEGUNDOS", "0.5")
    modulo = carregar_configuracao()
    assert modulo["RETENCAO_SEGUNDOS"] == 0.5
    # Desativa a espera real somente neste teste de configuração/validação.
    modulo["memoria"].__globals__["RETENCAO_SEGUNDOS"] = 0
    with TestClient(modulo["app"]) as client:
        assert client.get("/memoria", params={"tamanho_mb": minimo - 1}).status_code == 422
        assert client.get("/memoria", params={"tamanho_mb": maximo + 1}).status_code == 422
        for tamanho in [minimo, maximo]:
            assert client.get("/memoria", params={"tamanho_mb": tamanho}).status_code == 200
        response = client.get("/memoria")
        assert response.status_code == 200
        assert response.json()["tamanho_mb"] == padrao


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("MEMORY_LIMITE_MIN_MB", "0"),
        ("MEMORY_LIMITE_MIN_MB", "65"),
        ("MEMORY_LIMITE_MAX_MB", "0"),
        ("MEMORY_LIMITE_MAX_MB", "65"),  # 65 * 4 ultrapassa o orçamento.
        ("MEMORY_LIMITE_MAX_MB", "abc"),
        ("MEMORY_MAX_SIMULTANEAS", "0"),
        ("MEMORY_MAX_SIMULTANEAS", "5"),
        ("MEMORY_RETENCAO_SEGUNDOS", "-1"),
        ("MEMORY_RETENCAO_SEGUNDOS", "5.1"),
        ("MEMORY_RETENCAO_SEGUNDOS", "nan"),
        ("MEMORY_RETENCAO_SEGUNDOS", "inf"),
        ("MEMORY_RETENCAO_SEGUNDOS", "abc"),
    ],
)
def test_configuracao_invalida(monkeypatch, variavel, valor):
    monkeypatch.setenv(variavel, valor)
    with pytest.raises(ValueError):
        carregar_configuracao()
