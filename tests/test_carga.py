"""Validação do planejamento sem requisições à VM nem carga de estresse."""

import json
from importlib.util import find_spec
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.carga import executar_locust as carga


@pytest.mark.parametrize("argument,value", [
    ("--usuarios", "0"), ("--taxa", "0"), ("--taxa", "nan"),
    ("--limite", "-1"), ("--espera", "-1"), ("--espera", "inf"),
    ("--duracao", "1"), ("--aquecimento", "1"),
    ("--url", "http://usuario:senha@localhost:8001"),
    ("--url", "http://localhost:8001/primos"),
])
def test_parametros_invalidos(argument, value, tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as error:
        carga.main(["--cenario", "C1", "--usuarios", "1", argument, value])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_preparar_sem_http_e_sem_sobrescrever(tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda package: "teste")
    monkeypatch.setattr(carga.subprocess, "run", lambda *a, **k: pytest.fail("Carga indevida"))
    args = ["--cenario", "C3", "--usuarios", "5", "--taxa", "2", "--repeticao", "2",
            "--somente-preparar"]
    assert carga.main(args) == 0
    directory = tmp_path / "experimentos/resultados/carga/C3/usuarios_05/repeticao_02"
    data = json.loads((directory / "parametros.json").read_text(encoding="utf-8"))
    assert data["provisionamento_planejado"] == {"vcpus": 2, "ram_gib": 1, "workers": 2}
    assert not data["provisionamento_verificado_automaticamente"]
    assert [item["fase"] for item in data["fases"]] == ["aquecimento", "medicao"]
    assert all(item["estado"] == "planejado" for item in data["fases"])
    assert list(directory.iterdir()) == [directory / "parametros.json"]
    with pytest.raises(FileExistsError):
        carga.main(args)


@pytest.mark.parametrize("returncode,expected_calls", [(0, 2), (1, 1)])
def test_fases_e_falha_no_aquecimento(tmp_path, monkeypatch, returncode, expected_calls):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda package: "teste")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode)

    monkeypatch.setattr(carga.subprocess, "run", fake_run)
    assert carga.main(["--cenario", "C1", "--usuarios", "1"]) == returncode
    assert len(calls) == expected_calls
    assert "--headless" in calls[0]
    assert "--csv-full-history" in calls[0]
    assert "--reset-stats" in calls[0]
    assert calls[0][calls[0].index("--limite") + 1] == "100000"
    if len(calls) == 2:
        assert calls[0][calls[0].index("--csv") + 1] != calls[1][calls[1].index("--csv") + 1]
    path = tmp_path / "experimentos/resultados/carga/C1/usuarios_01/repeticao_01/parametros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert all(item["codigo_saida"] == returncode for item in data["fases"])
    assert all(item["tempo_parede_s"] >= 0 for item in data["fases"])


@pytest.mark.skipif(find_spec("locust") is None, reason="Instale requirements-carga.txt para validar Locust.")
def test_locustfile_sem_http_em_processo_isolado():
    # Locust aplica monkey patch gevent; não o importe no processo dos testes FastAPI.
    script = r'''
import argparse
import runpy
from types import SimpleNamespace
module = runpy.run_path("scripts/carga/locustfile.py")
parser = argparse.ArgumentParser()
module["argumentos"](parser)
assert parser.parse_args([]).limite == 100000
assert parser.parse_args(["--limite", "10", "--espera", "0"]).espera == 0
for converter, value in [("inteiro_positivo", "0"), ("espera_valida", "nan")]:
    try:
        module[converter](value)
    except argparse.ArgumentTypeError:
        pass
    else:
        raise AssertionError("Parâmetro inválido aceito")
class Response:
    def __init__(self, status, data):
        self.status_code, self.data, self.errors = status, data, []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def json(self):
        if self.data is None: raise ValueError()
        return self.data
    def failure(self, error): self.errors.append(error)
class Client:
    def get(self, path, **kwargs):
        assert path == "/primos"
        assert kwargs["params"] == {"limite": 10}
        assert kwargs["timeout"] == 30
        return response
user = SimpleNamespace(client=Client(), environment=SimpleNamespace(
    parsed_options=SimpleNamespace(limite=10, espera=1.5)))
assert module["UsuarioCPU"].wait_time(user) == 1.5
for status, data, failed in [
    (200, {"tipo": "CPU-bound", "limite": 10, "quantidade_primos": 4}, False),
    (422, {}, True), (200, None, True), (200, [], True),
    (200, {"tipo": "CPU-bound", "limite": 11, "quantidade_primos": 4}, True),
    (200, {"tipo": "CPU-bound", "limite": 10, "quantidade_primos": True}, True),
]:
    response = Response(status, data)
    module["UsuarioCPU"].primos(user)
    assert bool(response.errors) == failed
'''
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, "-c", script], cwd=root,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
