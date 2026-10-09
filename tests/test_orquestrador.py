"""Orquestração simulada: nenhuma chamada SSH, endpoint ou carga real."""

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from scripts.experimentacao import orquestrar as orch
from scripts.experimentacao import agente_linux as agent


def options(*args):
    return orch.parser().parse_args(["--id-execucao", "teste", "--cenario", "C4", "--aplicacao", "cpu",
                                     "--usuarios", "1", "--repeticao", "1", *args])


def test_matriz_completa_parametros_e_reserva():
    o = orch.parser().parse_args(["--id-execucao", "matriz"])
    jobs = orch.matriz(o)
    assert len(jobs) == 108
    assert {job["repeticao"] for job in jobs} == {1001, 1002, 1003}
    assert all(job["taxa"] == job["usuarios"] and job["espera_s"] == 0 for job in jobs)
    assert {job["usuarios"] for job in jobs if job["aplicacao"] == "memoria"} == {1, 2, 3}
    assert {job["usuarios"] for job in jobs if job["aplicacao"] == "io"} == {1, 2}
    assert orch.matriz(options("--tentativa", "2"))[0]["repeticao"] == 1011


def test_recuperacao_c3_r3012_e_filtros_das_16_planejadas():
    common = ["--id-execucao", "definitivos_C3_01", "--cenario", "C3", "--base-repeticao", "3000"]
    def jobs(*args):
        return orch.matriz(orch.parser().parse_args([*common, *args]))
    retry = jobs("--aplicacao", "cpu", "--usuarios", "10", "--repeticao", "2", "--tentativa", "2")
    assert len(retry) == 1 and retry[0]["repeticao"] == 3012
    assert retry[0]["repeticao_logica"] == 2 and retry[0]["tentativa"] == 2
    cpu = jobs("--aplicacao", "cpu", "--usuarios", "10", "--repeticao", "3")
    io, memory = jobs("--aplicacao", "io"), jobs("--aplicacao", "memoria")
    assert [len(cpu), len(io), len(memory)] == [1, 6, 9]
    assert cpu[0]["repeticao"] == 3003
    assert not any(j["aplicacao"] == "cpu" and j["repeticao"] == 3002 for j in [*cpu, *io, *memory])


def test_recuperacao_r2002_nova_tentativa_preserva_falha(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    args = ["--id-execucao", "recuperacao", "--cenario", "C4", "--aplicacao", "io",
            "--usuarios", "2", "--repeticao", "2", "--base-repeticao", "2000"]
    orch.main(args)  # Planejamento apenas, dentro do fixture isolado.
    campaign = tmp_path / "experimentos/resultados/orquestracao/recuperacao"
    failed = campaign / "io_C4_u02_r2002/manifesto.json"
    data = json.loads(failed.read_text(encoding="utf-8"))
    data["estado"] = "falha"
    failed.write_text(json.dumps(data), encoding="utf-8")
    original = failed.read_bytes()
    with pytest.raises(SystemExit):
        orch.main([*args, "--retomar"])
    assert failed.read_bytes() == original
    assert orch.main([*args, "--retomar", "--tentativa", "2"]) == 0
    assert failed.read_bytes() == original
    new = json.loads((campaign / "io_C4_u02_r2012/manifesto.json").read_text(encoding="utf-8"))
    assert new["job"]["repeticao_logica"] == 2
    assert new["job"]["tentativa"] == 2
    assert new["job"]["caminho"].endswith("repeticao_2012")


def test_planejar_padrao_sem_processos_ou_http(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **kw: pytest.fail("Subprocesso no planejamento"))
    monkeypatch.setattr(orch, "urlopen", lambda *a, **kw: pytest.fail("HTTP no planejamento"))
    args = ["--id-execucao", "plano", "--cenario", "C4", "--aplicacao", "cpu", "--usuarios", "1", "--repeticao", "1"]
    assert orch.main(args) == 0
    index = tmp_path / "experimentos/resultados/orquestracao/plano/indice.json"
    rows = json.loads(index.read_text(encoding="utf-8"))
    assert len(rows) == 1 and rows[0]["estado"] == "planejada"
    general = json.loads((index.parent.parent / "indice_geral.json").read_text(encoding="utf-8"))
    assert general[0]["campanha"] == "plano"
    assert not (tmp_path / "experimentos/resultados/carga").exists()
    assert orch.main([*args, "--retomar"]) == 0
    with pytest.raises(SystemExit):
        orch.main(args)


def test_planejamento_console_windows_cp1252(tmp_path):
    import os
    import sys
    code = "from pathlib import Path; import sys; from scripts.experimentacao import orquestrar as o; o.ROOT=Path(sys.argv[1]); o.main(['--id-execucao','console','--cenario','C4','--aplicacao','cpu','--usuarios','1','--repeticao','1'])"
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            env=dict(os.environ, PYTHONIOENCODING="cp1252"), timeout=20)
    assert result.returncode == 0, result.stderr
    assert b"PLANO cpu_C4_u01_r1001" in result.stdout


@pytest.mark.parametrize("args", [
    ["--executar"], ["--executar", "--confirmar-provisionamento", "C1"],
    ["--base-repeticao", "100"], ["--id-execucao", "../fora"], ["--usuarios", "40"],
    ["--timeout-ssh", "nan"], ["--duracao-monitor", "100"], ["--raiz-vm", "/x/../fora"],
    ["--raiz-vm", "/x;touch arquivo"], ["--ssh", "usuario:senha@host"],
])
def test_parametros_rejeitados_antes_de_executar(tmp_path, monkeypatch, args):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    with pytest.raises(SystemExit):
        orch.main(["--id-execucao", "teste", "--cenario", "C4", *args])
    assert not (tmp_path / "experimentos/resultados/carga").exists()


def test_colisao_e_reserva_preservam_arquivos(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    job = orch.matriz(options())[0]
    target = tmp_path / job["caminho"]
    target.mkdir(parents=True)
    original = target / "dados.txt"
    original.write_text("preservar")
    with pytest.raises(SystemExit):
        orch.main(["--id-execucao", "teste", "--cenario", "C4", "--aplicacao", "cpu", "--usuarios", "1", "--repeticao", "1"])
    assert original.read_text() == "preservar"
    lock = tmp_path / ".temp/poi_orquestrador.lock"
    lock.parent.mkdir(exist_ok=True)
    lock.write_text("outra execução")
    with pytest.raises(orch.Falha):
        with orch.reserva_local(tmp_path):
            pytest.fail("Reserva concorrente aceita")
    assert lock.read_text() == "outra execução"


def audit_data(app="cpu"):
    config = agent.PADROES_SERVIDOR[app].copy()
    if app == "memoria": config["MEMORY_RETENCAO_SEGUNDOS"] = 1
    if app == "io": config["IO_FSYNC"] = 1
    return dict(cpus=2, ram_total_bytes=2 * 1024 ** 3, servidores=[dict(aplicacao=app, workers=2,
        pid_principal=42, processos=[dict(pid=42, criado_epoch_s=100), dict(pid=43, criado_epoch_s=100)],
        configuracao_verificada=config, espaco_io_livre_bytes=1024 ** 3)])


@pytest.mark.parametrize("change", ["cpu", "ram", "workers", "pid", "retencao", "fsync", "espaco"])
def test_auditoria_incompativel_aborta(change):
    app = "memoria" if change == "retencao" else "io" if change in ("fsync", "espaco") else "cpu"
    data = audit_data(app)
    if change == "cpu": data["cpus"] = 1
    if change == "ram": data["ram_total_bytes"] = 1024 ** 3
    if change == "workers": data["servidores"][0]["workers"] = 1
    if change == "retencao": data["servidores"][0]["configuracao_verificada"]["MEMORY_RETENCAO_SEGUNDOS"] = 0
    if change == "fsync": data["servidores"][0]["configuracao_verificada"]["IO_FSYNC"] = 0
    if change == "espaco": data["servidores"][0]["espaco_io_livre_bytes"] = 1
    ops = SimpleNamespace(conferir_host=lambda: None, remoto=lambda request: data, health=lambda app: 999 if change == "pid" else 43)
    job = orch.matriz(options("--aplicacao", app))[0]
    with pytest.raises(orch.Falha):
        orch.verificar_ambiente(ops, [job])


def test_subprocesso_ssh_timeout_erro_e_comando_cotado(monkeypatch):
    ops = orch.Operacoes(options())
    def timeout(*a, **kw): raise subprocess.TimeoutExpired(a[0], 1)
    monkeypatch.setattr(orch.subprocess, "run", timeout)
    with pytest.raises(orch.Falha, match="Timeout"):
        ops.remoto({"acao": "auditar"})
    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, '{"erro":"configuração inválida"}', ""))
    with pytest.raises(orch.Falha, match="configuração inválida"):
        ops.remoto({"acao": "auditar"})
    monkeypatch.setattr(orch.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, '{"cpus":2}', ""))
    assert ops.remoto({"acao": "auditar"}) == {"cpus": 2}
    assert "BatchMode=yes" in ops.events[-1]["comando"]


def test_prontidao_por_estado_sem_atraso_fixo(monkeypatch):
    states = iter([dict(vivo=True, pronto=False), dict(vivo=True, pronto=True)])
    ops = SimpleNamespace(o=options(), remoto=lambda req: next(states))
    sleeps = []
    monkeypatch.setattr(orch.time, "sleep", sleeps.append)
    assert orch.aguardar(ops, "token", True)["pronto"]
    assert sleeps == [1]
    ops.remoto = lambda req: dict(vivo=False, pronto=False, metadados={"estado": "erro"})
    with pytest.raises(orch.Falha):
        orch.aguardar(ops, "token", True)


def probe(path, offset=0):
    orch.salvar(path, {"menor_incerteza": {"offset_estimado_s": offset,
        "offset_servidor_menos_cliente_min_s": offset - .01, "offset_servidor_menos_cliente_max_s": offset + .01}})


def test_relogios_nao_sobrepostos_nao_definitivos(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    probe(a)
    probe(b, .1)
    with pytest.raises(orch.Falha, match="não se sobrepõem"):
        orch.conferir_relogios(a, b)


class FakeOps:
    def __init__(self, root, outcome=None):
        self.o = options()
        self.root, self.events, self.actions, self.outcome = root, [], [], outcome
    def conferir_host(self): pass
    def health(self, app): return 43
    def remoto(self, req):
        self.actions.append(req["acao"])
        if req["acao"] == "auditar": return audit_data()
        if req["acao"] == "iniciar": return dict(monitoramento="/vm/monitoramento_linux")
        if req["acao"] == "encerrar": return {}
        return dict(vivo=False, metadados=dict(estado="ctrl_c"))
    def sondar(self, app, path): probe(path)
    def local(self, command, logfile, timeout):
        if self.outcome: raise self.outcome
        job = orch.matriz(options())[0]
        target = self.root / job["caminho"]
        target.mkdir(parents=True)
        metadata = {"parametros": {key: job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")},
            "fases": [dict(fase="aquecimento", instrumentacao=dict(usuarios_prontos_utc="2026-10-08T12:00:02Z")),
                      dict(fase="medicao", instrumentacao=dict(encerramento_inicio_utc="2026-10-08T12:01:30Z"))]}
        orch.salvar(target / "parametros.json", metadata)
        (target / "medicao_latencias.csv").write_text("latencias sintéticas")
    def copiar(self, remote, target):
        target.mkdir()
        job = orch.matriz(options())[0]
        orch.salvar(target / "metadados.json", {key: job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")})
        (target / "sistema.csv").write_text("utc\n2026-10-08T12:00:01Z\n2026-10-08T12:01:31Z\n")
    def run(self, command, timeout):
        output = Path(command[-1])
        output.mkdir()
        (output / "consolidado.csv").write_text("p95_janela_ms,latencias_janela_n,req_janela,amostras_sistema,avisos\n10,5,5,89,CPU global inconsistente\n")
        (output / "resumo.txt").write_text("Resumo sintético")


def setup_job(tmp_path):
    campaign = tmp_path / "campanha"
    path = campaign / "cpu_C4_u01_r1001/manifesto.json"
    path.parent.mkdir(parents=True)
    job = orch.matriz(options())[0]
    manifest = dict(job=job, manifesto=str(path), estado="planejada")
    return campaign, path, job, manifest


def test_fluxo_completo_ordem_e_avisos_preservados(tmp_path, monkeypatch):
    campaign, path, job, manifest = setup_job(tmp_path)
    ops = FakeOps(tmp_path)
    calls = []
    def wait(ops, token, ready):
        calls.append(ready)
        return dict(metadados={key: job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")})
    monkeypatch.setattr(orch, "aguardar", wait)
    orch.executar_job(ops, job, manifest, path, campaign)
    assert calls == [True, False]
    assert manifest["estado"] == "concluída"
    assert "CPU global inconsistente" in manifest["avisos"]
    assert manifest["artefatos_sha256"]
    assert "encerrar" not in ops.actions
    assert json.loads((tmp_path / job["caminho"] / "parametros.json").read_text())["configuracao_servidor_verificada"]


@pytest.mark.parametrize("error,state", [(orch.Falha("Locust falhou"), "falha"),
    (subprocess.TimeoutExpired("Locust", 1), "falha"), (KeyboardInterrupt(), "interrompida")])
def test_falha_timeout_ctrlc_preservam_estado_e_encerram_so_monitor(tmp_path, monkeypatch, error, state):
    campaign, path, job, manifest = setup_job(tmp_path)
    ops = FakeOps(tmp_path, error)
    monkeypatch.setattr(orch, "aguardar", lambda *a, **kw: {})
    with pytest.raises(type(error)):
        orch.executar_job(ops, job, manifest, path, campaign)
    assert manifest["estado"] == state
    assert ops.actions[-2:] == ["encerrar", "estado"]
    assert (path.parent / "relogio_depois.json").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["estado"] == state


def test_retomada_exige_nova_tentativa_sem_sobrescrever(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    args = ["--id-execucao", "teste", "--cenario", "C4", "--aplicacao", "cpu", "--usuarios", "1", "--repeticao", "1"]
    orch.main(args)
    path = tmp_path / "experimentos/resultados/orquestracao/teste/cpu_C4_u01_r1001/manifesto.json"
    data = json.loads(path.read_text())
    data["estado"] = "interrompida"
    orch.salvar(path, data)
    before = path.read_bytes()
    with pytest.raises(SystemExit): orch.main([*args, "--retomar"])
    assert orch.main([*args, "--retomar", "--tentativa", "2"]) == 0
    assert path.read_bytes() == before
    assert path.with_name("manifesto.json").exists()


def test_agente_nao_sinaliza_pid_reutilizado(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    token = "c9bf50b3-ecf1-4df7-b188-e94417c7e223"
    base = agent.pasta(token)
    base.mkdir(parents=True)
    agent.gravar(base / "controle.json", dict(pid=42, criado_epoch_s=100, comando=["monitor"], monitoramento=str(tmp_path / "monitor")))
    monkeypatch.setattr(agent.psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 200, cmdline=lambda: ["outro"]))
    monkeypatch.setattr(agent.os, "kill", lambda *args: pytest.fail("PID reutilizado sinalizado"))
    assert not agent.stop({"token": token})["vivo"]


def test_falha_no_primeiro_job_nao_inicia_proximo(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: name)
    ops = FakeOps(tmp_path, orch.Falha("erro inesperado"))
    monkeypatch.setattr(orch, "Operacoes", lambda options: ops)
    monkeypatch.setattr(orch, "aguardar", lambda *a, **kw: {})
    with pytest.raises(SystemExit) as error:
        orch.main(["--id-execucao", "execucao", "--executar", "--cenario", "C4", "--confirmar-provisionamento", "C4",
                   "--aplicacao", "cpu", "--usuarios", "1"])
    assert error.value.code == 1
    assert ops.actions.count("iniciar") == 1
    assert not list((tmp_path / "experimentos/resultados/orquestracao/execucao").glob("*1002"))


def test_validar_ambiente_nao_inicia_locust(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: name)
    ops = FakeOps(tmp_path)
    monkeypatch.setattr(orch, "Operacoes", lambda options: ops)
    monkeypatch.setattr(ops, "local", lambda *a, **kw: pytest.fail("Locust indevido"))
    assert orch.main(["--id-execucao", "validacao", "--validar-ambiente", "--cenario", "C4", "--aplicacao", "cpu"]) == 0
    assert ops.actions == ["auditar"]
    assert list((tmp_path / "experimentos/resultados/orquestracao/validacao").glob("validacao_*.json"))


@pytest.mark.parametrize("case", ["ok", "retencao_ausente", "workers_ausentes", "codigo_alterado"])
def test_auditoria_linux_processos_ambiente_e_defaults(tmp_path, monkeypatch, case):
    monkeypatch.setattr(agent, "ROOT", tmp_path)
    original = Path(__file__).resolve().parents[1] / "apps/memory_bound/main.py"
    source = tmp_path / "apps/memory_bound/main.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(original.read_bytes())
    wrapper = tmp_path / "scripts/monitoramento/servidor_experimental.py"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("# código simulado")
    created = max(source.stat().st_mtime, wrapper.stat().st_mtime) + 10
    env = {"POI_APLICACAO": "memoria", "POI_DIAGNOSTICO": "1"}
    if case != "retencao_ausente": env["MEMORY_RETENCAO_SEGUNDOS"] = "1"
    class Process:
        def __init__(self, pid): self.pid = pid
        def cmdline(self):
            return ["python", "-m", "uvicorn", "scripts.monitoramento.servidor_experimental:criar_app", "--workers", "2"] if self.pid == 42 else ["python", "--multiprocessing-fork"]
        def environ(self): return env
        def create_time(self): return 1 if case == "codigo_alterado" else created
        def status(self): return "running"
        def net_connections(self, kind):
            return [SimpleNamespace(status=agent.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=8002))]
        def ppid(self): return 1 if self.pid == 42 else 42
        def parents(self): return [] if self.pid == 42 else [Process(42)]
        def children(self, recursive): return [] if case == "workers_ausentes" else [Process(43), Process(44)]
    monkeypatch.setattr(agent.psutil, "Process", Process)
    monkeypatch.setattr(agent.psutil, "net_connections", lambda kind: [SimpleNamespace(pid=pid,
        status=agent.psutil.CONN_LISTEN, laddr=SimpleNamespace(port=8002)) for pid in (44,)])
    if case in ("workers_ausentes", "codigo_alterado"):
        with pytest.raises(ValueError): agent.auditar("memoria")
    else:
        result = agent.auditar("memoria")
        assert result["pid_principal"] == 42 and result["workers"] == 2
        assert result["codigo_sha256"]
        assert result["configuracao_verificada"]["MEMORY_RETENCAO_SEGUNDOS"] == (0 if case == "retencao_ausente" else 1)
        assert result["processos"][0]["defaults_utilizados"]["MEMORY_LIMITE_MAX_MB"] == "64"


def test_scp_destino_existente_recusado(tmp_path, monkeypatch):
    ops = orch.Operacoes(options())
    monkeypatch.setattr(ops, "run", lambda *a, **kw: pytest.fail("SCP sobrescreveria dados"))
    with pytest.raises(orch.Falha): ops.copiar("/vm/monitor", tmp_path)


def test_prontidao_timeout(monkeypatch):
    clock = iter([0, 0, 100])
    monkeypatch.setattr(orch.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(orch.time, "sleep", lambda interval: None)
    ops = SimpleNamespace(o=options(), remoto=lambda req: dict(vivo=True, pronto=False))
    with pytest.raises(orch.Falha, match="Timeout"):
        orch.aguardar(ops, "token", True)


@pytest.mark.parametrize("outcome", [0, 1, "timeout", "ctrlc"])
def test_popen_local_codigo_saida_timeout_e_interrupcao(tmp_path, monkeypatch, outcome):
    ops = orch.Operacoes(options())
    ops.root = tmp_path
    process = SimpleNamespace(pid=42, stdin=SimpleNamespace(close=lambda: None))
    def wait(timeout):
        if outcome == "timeout": raise subprocess.TimeoutExpired("comando", timeout)
        if outcome == "ctrlc": raise KeyboardInterrupt()
        return outcome
    process.wait = wait
    def popen(*a, **kw):
        assert kw["stdin"] == subprocess.PIPE
        return process
    monkeypatch.setattr(orch.subprocess, "Popen", popen)
    import psutil
    monkeypatch.setattr(psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 100))
    stopped = []
    monkeypatch.setattr(ops, "parar_local", stopped.append)
    if outcome == 0:
        ops.local(["comando"], tmp_path / "console.txt", 1)
        assert not stopped
    else:
        expected = orch.Falha if outcome == 1 else subprocess.TimeoutExpired if outcome == "timeout" else KeyboardInterrupt
        with pytest.raises(expected):
            ops.local(["comando"], tmp_path / "console.txt", 1)
        assert bool(stopped) == (outcome != 1)


def test_encerramento_local_recusa_pid_reutilizado(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 200))
    process = SimpleNamespace(pid=42, poi_identity=100, poll=lambda: None,
                              send_signal=lambda signal: pytest.fail("Outro processo sinalizado"))
    with pytest.raises(orch.Falha, match="PID local mudou"):
        orch.Operacoes.parar_local(process)


def test_retomada_concluida_confere_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(orch, "ROOT", tmp_path)
    args = ["--id-execucao", "teste", "--cenario", "C4", "--aplicacao", "cpu", "--usuarios", "1", "--repeticao", "1"]
    orch.main(args)
    campaign = tmp_path / "experimentos/resultados/orquestracao/teste"
    path = campaign / "cpu_C4_u01_r1001/manifesto.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    job = manifest["job"]
    monkeypatch.setattr(orch, "aguardar", lambda *a, **kw: dict(metadados={key: job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")}))
    orch.executar_job(FakeOps(tmp_path), job, manifest, path, campaign)
    original = path.read_bytes()
    assert orch.main([*args, "--retomar"]) == 0
    assert path.read_bytes() == original
    (Path(manifest["analise"]) / "consolidado.csv").write_text("arquivo incompleto")
    with pytest.raises(SystemExit): orch.main([*args, "--retomar"])
