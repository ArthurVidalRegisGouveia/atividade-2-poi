"""Perfis, nomes, diagnóstico e disco com mocks; nenhuma carga na VM."""

import csv
from importlib.util import find_spec
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from scripts.carga import executar_locust as executor
from scripts.carga.perfis import configurar_servidor, pedido, resposta_valida
from scripts.monitoramento import servidor_experimental as servidor


@pytest.mark.parametrize("app,port,params", [("cpu", 8001, {"limite": 100000}),
    ("memoria", 8002, {"tamanho_mb": 50}), ("io", 8003, {"tamanho_mb": 10, "operacoes": 1})])
def test_planejamento_aplicacao_caminho_parametros(tmp_path, monkeypatch, app, port, params):
    monkeypatch.setattr(executor, "ROOT", tmp_path)
    monkeypatch.setattr(executor, "version", lambda _: "teste")
    monkeypatch.setattr(executor.subprocess, "run", lambda *a, **kw: pytest.fail("HTTP indevido"))
    assert executor.main(["--cenario", "C4", "--usuarios", "2", "--aplicacao", app, "--somente-preparar"]) == 0
    path = tmp_path / f"experimentos/resultados/carga/{app}/C4/usuarios_02/repeticao_01/parametros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["aplicacao"] == app
    assert data["parametros_http"] == params
    assert data["parametros"]["url"] == f"http://127.0.0.1:{port}"
    assert not data["configuracao_servidor_verificada"]
    assert "--latencias-saida" in data["fases"][1]["comando"]


@pytest.mark.parametrize("app,args", [("cpu", ["--tamanho-mb", "1"]),
    ("cpu", ["--retencao-segundos", "1"]), ("memoria", ["--fsync", "1"]),
    ("memoria", ["--retencao-segundos", "6"]), ("memoria", ["--tamanho-mb", "65"]),
    ("memoria", ["--operacoes", "2"]), ("io", ["--tamanho-mb", "33"]),
    ("io", ["--operacoes", "6"]), ("io", ["--retencao-segundos", "1"]),
    ("io", ["--fsync", "2"]), ("io", ["--tamanho-mb", "0"])])
def test_parametros_incompativeis_rejeitados(tmp_path, monkeypatch, app, args):
    monkeypatch.setattr(executor, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        executor.main(["--cenario", "C1", "--usuarios", "1", "--aplicacao", app, "--somente-preparar", *args])
    assert not list(tmp_path.iterdir())


def test_configuracao_servidor_declarada_nao_parametro_http(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "ROOT", tmp_path)
    monkeypatch.setattr(executor, "version", lambda _: "teste")
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"IO_TAMANHO_MAX_MB": 16, "IO_DIRETORIO_TEMP": ".temp/io_teste", "IO_FSYNC": 1}))
    executor.main(["--cenario", "C1", "--usuarios", "1", "--aplicacao", "io", "--fsync", "1",
                   "--config-servidor", str(source), "--somente-preparar"])
    path = tmp_path / "experimentos/resultados/carga/io/C1/usuarios_01/repeticao_01/parametros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["configuracao_servidor_declarada"]["IO_FSYNC"] == 1
    assert "fsync" not in data["parametros_http"]
    assert "--fsync" not in data["fases"][1]["comando"]
    with pytest.raises(ValueError):
        configurar_servidor("io", {"IO_FSYNC": 0}, fsync=1)
    with pytest.raises(ValueError):
        configurar_servidor("io", {"senha": "segredo"})


@pytest.mark.parametrize("app,config", [
    ("cpu", {"CPU_DIAGNOSTICO": 2}), ("cpu", {"CPU_LIMITE_MAX": 0}),
    ("memoria", {"MEMORY_LIMITE_MAX_MB": 100}), ("memoria", {"MEMORY_LIMITE_MIN_MB": 65}),
    ("memoria", {"MEMORY_RETENCAO_SEGUNDOS": "nan"}), ("io", {"IO_MAX_SIMULTANEAS": 10}),
    ("io", {"IO_OPERACOES_MAX": 10}), ("io", {"IO_TAMANHO_MAX_MB": "2.5"}),
])
def test_configuracoes_servidor_invalidas(app, config):
    with pytest.raises(ValueError):
        configurar_servidor(app, config)


@pytest.mark.parametrize("app,module", [("cpu", "cpu_bound"), ("memoria", "memory_bound"), ("io", "io_bound")])
@pytest.mark.parametrize("diagnostic", ["0", "1"])
def test_factory_diagnostico_opcional_sem_mudar_corpo(monkeypatch, app, module, diagnostic):
    api = FastAPI()
    @api.get("/health")
    def health():
        return {"status": "ok"}
    def load(name):
        assert name == f"apps.{module}.main"
        return SimpleNamespace(app=api)
    monkeypatch.setattr(servidor, "import_module", load)
    monkeypatch.setenv("POI_APLICACAO", app)
    monkeypatch.setenv("POI_DIAGNOSTICO", diagnostic)
    with TestClient(servidor.criar_app()) as client:
        response = client.get("/health")
    assert response.json() == {"status": "ok"}
    assert ("X-Worker-PID" in response.headers) == (diagnostic == "1")
    assert ("X-Server-Sent-UTC" in response.headers) == (diagnostic == "1")


@pytest.mark.parametrize("app,params,data", [
    ("cpu", {"limite": 10}, {"tipo": "CPU-bound", "limite": 10, "quantidade_primos": 4}),
    ("memoria", {"tamanho_mb": 1}, {"tipo": "Memory-bound", "tamanho_mb": 1, "verificacao": 257}),
    ("io", {"tamanho_mb": 1, "operacoes": 2}, {"tipo": "I/O-bound", "tamanho_mb": 1, "operacoes": 2,
        "bytes_escritos": 2097152, "bytes_lidos": 2097152, "bytes_processados": 4194304, "verificacao": "ok"}),
])
def test_respostas_por_perfil(app, params, data):
    assert resposta_valida(app, params, data)
    wrong = dict(data, tipo="outro")
    assert not resposta_valida(app, params, wrong)
    wrong = dict(data)
    wrong[next(iter(params))] = True
    assert not resposta_valida(app, params, wrong)


@pytest.mark.skipif(find_spec("locust") is None, reason="Instale requirements-carga.txt")
@pytest.mark.parametrize("app", ["cpu", "memoria", "io"])
def test_locust_rotas_e_latencias_tres_perfis_em_processo_isolado(app, tmp_path):
    code = r'''
import runpy, sys, json, csv
from pathlib import Path
from types import SimpleNamespace
from locust.event import Events
m=runpy.run_path("scripts/carga/locustfile.py")
app, directory=sys.argv[1],Path(sys.argv[2])
options=SimpleNamespace(aplicacao=app,limite=10,tamanho_mb=1,operacoes=1,espera=0,conexoes="fechar",
    diagnostico_saida=str(directory/"marcos.json"),latencias_saida=str(directory/"latencias.csv"),limite_latencias=10)
env=SimpleNamespace(events=Events(),parsed_options=options)
m["instrumentar"](env)
endpoint, params=m["pedido"](options)
data={"tipo":{"cpu":"CPU-bound","memoria":"Memory-bound","io":"I/O-bound"}[app],**params}
data.update(quantidade_primos=4,verificacao=257 if app=="memoria" else "ok",
    bytes_escritos=1048576,bytes_lidos=1048576,bytes_processados=2097152)
class Response:
    status_code=200
    headers={}
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def json(self): return data
    def failure(self,reason): raise AssertionError(reason)
class Client:
    def get(self,path,**kwargs):
        assert path==endpoint and kwargs["params"]==params
        assert kwargs["headers"]=={"Connection":"close"}
        return Response()
m["UsuarioCPU"].primos(SimpleNamespace(environment=env,client=Client()))
env.events.test_start.fire()
env.events.request.fire(name=endpoint,response_time=99)
env.events.spawning_complete.fire(user_count=1)
env.events.request.fire(name=endpoint,response_time=12)
env.events.test_stopping.fire()
env.events.request.fire(name=endpoint,response_time=99)
env.events.test_stop.fire()
with (directory/"latencias.csv").open(newline="") as source:
    rows=list(csv.DictReader(source))
assert len(rows)==1 and float(rows[0]["latencia_ms"])==12
assert json.loads((directory/"marcos.json").read_text())["latencias"]["completo"]
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, app, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_discos_deltas_resets_e_indisponibilidade(monkeypatch):
    from scripts.monitoramento import monitorar_linux as monitor
    clock = SimpleNamespace(value=0)
    values = SimpleNamespace(read_bytes=100, write_bytes=200, read_count=1, write_count=2, busy_time=10)
    monkeypatch.setattr(monitor.time, "monotonic", lambda: clock.value)
    monkeypatch.setattr(monitor.psutil, "disk_io_counters", lambda **kwargs: {"vda": values})
    collector = monitor.ColetorDiscos()
    assert collector.sample(1, 0)[0]["leitura_bytes_delta"] is None
    clock.value = 2
    values.read_bytes += 40
    values.write_bytes += 60
    values.busy_time += 5
    row = collector.sample(2, 2)[0]
    assert row["leitura_bytes_delta"] == 40
    assert row["escrita_bytes_s"] == 30
    assert row["ocupado_ms_delta"] == 5
    clock.value = 3
    values.read_bytes = 0
    row = collector.sample(3, 3)[0]
    assert row["erro"] == "contador_reiniciado"
    assert row["leitura_bytes_s"] is None
    monkeypatch.setattr(monitor.psutil, "disk_io_counters", lambda **kwargs: None)
    assert collector.sample(4, 4)[0]["erro"] == "contadores_indisponiveis"
