"""Validação do planejamento sem requisições à VM nem carga de estresse."""

import json
import csv
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.carga import executar_locust as carga



def artefatos_validos(command):
    prefix = Path(command[command.index("--csv") + 1])
    users = int(command[command.index("--users") + 1])
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=10)
    def write(path, rows):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    write(Path(str(prefix) + "_stats.csv"), [{"Name": "Aggregated", "Request Count": 2}])
    write(Path(str(prefix) + "_stats_history.csv"), [
        {"Name": "Aggregated", "Timestamp": (start + timedelta(seconds=t)).timestamp(),
         "User Count": users} for t in (2, 5)])
    data = {"usuarios_prontos_utc": start.isoformat(), "encerramento_inicio_utc": end.isoformat(),
            "eventos_usuarios": [{"usuarios": users}]}
    if "--latencias-saida" in command:
        write(Path(command[command.index("--latencias-saida") + 1]), [{"latencia_ms": 10}])
        data["latencias"] = {"registros": 1, "completo": True}
    Path(command[command.index("--diagnostico-saida") + 1]).write_text(json.dumps(data), encoding="utf-8")
    return data


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
    directory = tmp_path / "experimentos/resultados/carga/cpu/C3/usuarios_05/repeticao_02"
    data = json.loads((directory / "parametros.json").read_text(encoding="utf-8"))
    assert data["provisionamento_planejado"] == {"vcpus": 2, "ram_gib": 1, "workers": 2}
    assert not data["provisionamento_verificado_automaticamente"]
    assert [item["fase"] for item in data["fases"]] == ["aquecimento", "medicao"]
    assert all(item["estado"] == "planejado" for item in data["fases"])
    assert "--latencias-saida" not in data["fases"][0]["comando"]
    assert "--latencias-saida" in data["fases"][1]["comando"]
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
        assert kwargs["stdin"] == subprocess.PIPE
        artefatos_validos(command)
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
    path = tmp_path / "experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/parametros.json"
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
assert parser.parse_args([]).conexoes == "reutilizar"
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
        assert kwargs["headers"] == ({"Connection": "close"} if getattr(user.environment.parsed_options, "conexoes", "reutilizar") == "fechar" else {})
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
from collections import Counter
user.environment.parsed_options.conexoes = "fechar"
user.environment.parsed_options.registrar_worker_pid = True
user.environment.worker_counts = Counter()
response = Response(200, {"tipo": "CPU-bound", "limite": 10, "quantidade_primos": 4})
response.headers = {"X-Worker-PID": "1165"}
module["UsuarioCPU"].primos(user)
assert user.environment.worker_counts["1165/HTTP_200"] == 1
response.headers = {}
module["UsuarioCPU"].primos(user)
assert user.environment.worker_counts["ausente_ou_invalido/HTTP_200"] == 1
import tempfile, json
from pathlib import Path
from locust.event import Events
with tempfile.TemporaryDirectory() as directory:
    env = SimpleNamespace(events=Events(), parsed_options=SimpleNamespace(
        diagnostico_saida=str(Path(directory)/"marcos.json"), conexoes="fechar", registrar_worker_pid=True,
        latencias_saida=str(Path(directory)/"latencias.csv"), limite_latencias=10))
    module["instrumentar"](env)
    env.events.test_start.fire()
    env.events.request.fire(name="/primos", response_time=99, exception=None)
    env.worker_counts["rampa"] = 1
    env.events.spawning_complete.fire(user_count=2)
    assert not env.worker_counts
    env.events.request.fire(name="/health", response_time=99, exception=None)
    env.events.request.fire(name="/primos", response_time=10, exception=None)
    env.events.request.fire(name="/primos", response_time=30, exception=ValueError("falha"))
    env.worker_counts["1165/HTTP_200"] = 3
    env.events.test_stopping.fire()
    env.events.request.fire(name="/primos", response_time=99, exception=None)
    env.worker_counts["1165/HTTP_200"] += 1
    env.events.test_stop.fire()
    data = json.loads(Path(directory,"marcos.json").read_text())
    assert data["pids_janela"]["1165/HTTP_200"] == 3
    assert data["pids_apos_encerramento"]["1165/HTTP_200"] == 4
    assert data["latencias"]["completo"]
    assert data["latencias"]["registros"] == 2
    import csv
    with Path(directory,"latencias.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert [float(row["latencia_ms"]) for row in rows] == [10,30]
    assert [row["falha"] for row in rows] == ["0","1"]
    assert all(data[field].endswith("+00:00") for field in (
        "fase_inicio_utc", "usuarios_prontos_utc", "encerramento_inicio_utc", "fase_fim_utc"))
with tempfile.TemporaryDirectory() as directory:
    env = SimpleNamespace(events=Events(), parsed_options=SimpleNamespace(
        num_users=2, diagnostico_saida=str(Path(directory)/"marcos.json"),
        latencias_saida=str(Path(directory)/"latencias.csv"), limite_latencias=10))
    module["instrumentar"](env)
    env.events.test_start.fire()
    env.events.spawning_complete.fire(user_count=0)
    assert "usuarios_prontos_utc" not in env.instrumentacao
    env.events.spawning_complete.fire(user_count=2)
    original = env.instrumentacao["usuarios_prontos_utc"]
    env.events.request.fire(name="/primos", response_time=10, exception=None)
    env.events.spawning_complete.fire(user_count=0)
    assert env.instrumentacao["usuarios_prontos_utc"] == original
    env.events.request.fire(name="/primos", response_time=99, exception=None)
    env.events.test_stopping.fire()
    env.events.test_stop.fire()
    assert env.instrumentacao["latencias"]["registros"] == 1
    assert [e["usuarios"] for e in env.instrumentacao["eventos_usuarios"]] == [0,2,0]
'''
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, "-c", script], cwd=root,
                               capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("mode", ["reutilizar", "fechar"])
def test_parametros_conexao_e_metadados(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda _: "teste")
    carga.main(["--cenario", "C4", "--usuarios", "2", "--conexoes", mode,
                "--registrar-worker-pid", "--somente-preparar"])
    path = tmp_path / "experimentos/resultados/carga/cpu/C4/usuarios_02/repeticao_01/parametros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["parametros"]["conexoes"] == mode
    assert data["parametros"]["registrar_worker_pid"]
    assert "--registrar-worker-pid" in data["fases"][0]["comando"]
    assert "--diagnostico-saida" in data["fases"][0]["comando"]


def test_executor_incorpora_marcos_e_relogio(tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda _: "teste")
    clock_file = tmp_path / "relogio.json"
    clock_file.write_text(json.dumps({"url": "http://127.0.0.1:8001", "menor_incerteza": {
        "offset_estimado_s": -3, "incerteza_meia_faixa_s": .1}}), encoding="utf-8")

    def fake_run(command, **kwargs):
        artefatos_validos(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(carga.subprocess, "run", fake_run)
    carga.main(["--cenario", "C4", "--usuarios", "2", "--verificacao-relogio", str(clock_file)])
    metadata = json.loads((tmp_path / "experimentos/resultados/carga/cpu/C4/usuarios_02/repeticao_01/parametros.json").read_text())
    assert metadata["verificacao_relogio"]["menor_incerteza"]["offset_estimado_s"] == -3
    assert all("instrumentacao" in phase for phase in metadata["fases"])


def test_relogio_de_outro_alvo_rejeitado(tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    clock_file = tmp_path / "relogio.json"
    clock_file.write_text(json.dumps({"url": "http://outro:8001", "menor_incerteza": {}}))
    with pytest.raises(SystemExit):
        carga.main(["--cenario", "C4", "--usuarios", "2", "--verificacao-relogio", str(clock_file)])
    assert not (tmp_path / "experimentos").exists()


@pytest.mark.parametrize("value", ["0", "1000001"])
def test_limite_latencias_executor(value, tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        carga.main(["--cenario", "C1", "--usuarios", "1", "--limite-latencias", value, "--somente-preparar"])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("problem", ["usuarios_zero", "sem_requisicoes", "csv_fechado", "stopping", "ausentes", "latencias_vazias"])
def test_codigo_zero_nao_valida_fase(tmp_path, monkeypatch, problem):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda _: "teste")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        data = artefatos_validos(command)
        prefix = Path(command[command.index("--csv") + 1])
        if prefix.name == "medicao":
            if problem == "usuarios_zero":
                path = Path(str(prefix) + "_stats_history.csv")
                rows = list(csv.DictReader(path.open(encoding="utf-8")))
                for row in rows: row["User Count"] = 0
                with path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
            elif problem == "sem_requisicoes":
                Path(str(prefix) + "_stats.csv").write_text("Name,Request Count\nAggregated,0\n")
            elif problem in ("csv_fechado", "stopping"):
                kwargs["stdout"].write("ValueError: I/O operation on closed file" if problem == "csv_fechado"
                                       else "Tried to stop User in an unexpected state: stopping")
            elif problem == "ausentes":
                Path(command[command.index("--diagnostico-saida") + 1]).write_text("{}")
            else:
                data["latencias"]["registros"] = 0
                Path(command[command.index("--diagnostico-saida") + 1]).write_text(json.dumps(data))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(carga.subprocess, "run", run)
    assert carga.main(["--cenario", "C4", "--usuarios", "2"]) == 2
    path = tmp_path / "experimentos/resultados/carga/cpu/C4/usuarios_02/repeticao_01/parametros.json"
    phase = json.loads(path.read_text(encoding="utf-8"))["fases"][-1]
    assert len(calls) == 2 and phase["estado"] == "falha"
    assert phase["codigo_saida"] == 0 and phase["erros_validacao"]


@pytest.mark.skipif(find_spec("locust") is None, reason="Locust não instalado")
def test_locust_sem_terminal_desabilita_atalhos():
    # Exercita a biblioteca instalada sem usuários HTTP nem servidor.
    script = '''
import sys
from locust.input_events import input_listener
called = []
assert not sys.stdin.isatty()
input_listener({"S": lambda: called.append("reduzir usuarios")})()
assert not called
'''
    result = subprocess.run([sys.executable, "-c", script], stdin=subprocess.PIPE,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_falha_semantica_aquecimento_impede_medicao(tmp_path, monkeypatch):
    monkeypatch.setattr(carga, "ROOT", tmp_path)
    monkeypatch.setattr(carga, "version", lambda _: "teste")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        artefatos_validos(command)
        kwargs["stdout"].write("Tried to stop User in an unexpected state: stopping")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(carga.subprocess, "run", run)
    assert carga.main(["--cenario", "C4", "--usuarios", "2"]) == 2
    assert len(calls) == 1
    assert calls[0][calls[0].index("--csv") + 1].endswith("aquecimento")
