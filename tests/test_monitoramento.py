"""Testes com dados simulados; não validam empiricamente a coleta Linux."""

import csv
import json
from collections import namedtuple
from types import SimpleNamespace

import pytest

psutil = pytest.importorskip("psutil", reason="Instale requirements-monitoramento.txt")
from scripts.monitoramento import monitorar_linux as monitor


class Processo:
    def __init__(self, pid, created=100):
        self.pid, self.created = pid, created
        self.alive, self.denied = True, False
        self.cpu, self.children_list = 0, []

    def is_running(self): return self.alive
    def status(self): return "running"
    def create_time(self): return self.created
    def children(self, recursive):
        assert recursive
        return self.children_list
    def cpu_times(self):
        if self.denied: raise psutil.AccessDenied(self.pid)
        return namedtuple("Cpu", "user system children_user")(self.cpu, 0, 999)
    def memory_info(self):
        if not self.alive: raise psutil.NoSuchProcess(self.pid)
        return SimpleNamespace(rss=100, vms=200)
    def memory_full_info(self): return SimpleNamespace(uss=60, pss=80)


@pytest.fixture
def environment(monkeypatch):
    root = Processo(42)
    root.children_list = [Processo(43)]
    monkeypatch.setattr(monitor.psutil, "Process", lambda pid: root if pid == 42 else pytest.fail("PID externo"))
    monkeypatch.setattr(monitor.psutil, "cpu_count", lambda logical: 2)
    monkeypatch.setattr(monitor.psutil, "cpu_percent", lambda interval: 50)
    monkeypatch.setattr(monitor.psutil, "virtual_memory", lambda: SimpleNamespace(
        total=1000, available=600, used=300, percent=40))
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(monitor.time, "monotonic", lambda: clock.value)
    return root, clock


def test_metricas_e_normalizacao(environment):
    root, clock = environment
    collector = monitor.Coletor(42, detailed=True)
    system, rows = collector.sample(1, 0, 0)
    assert system["cpu_soma_uma_cpu_pct"] is None
    assert system["rss_soma_bytes"] == 200
    assert system["uss_soma_bytes"] == 120
    assert system["pss_soma_bytes"] == 160
    assert system["ram_usada_psutil_bytes"] == 300
    assert system["ram_nao_disponivel_bytes"] == 400
    assert system["cpu_sistema_capacidade_pct"] == 50
    assert {r["pid"] for r in rows} == {42, 43}
    assert rows[0]["papel"] == "principal"
    clock.value = 1
    root.cpu = 0.5
    root.children_list[0].cpu = 1
    system, rows = collector.sample(2, 1, 1)
    assert system["cpu_soma_uma_cpu_pct"] == 150
    assert system["cpu_soma_capacidade_vm_pct"] == 75
    assert system["cpu_processos_completa"]
    assert json.loads(system["processos_adicionados"]) == []


def test_alteracoes_e_reutilizacao_pid(environment):
    root, clock = environment
    collector = monitor.Coletor(42)
    collector.sample(1, 0, 0)
    root.children_list = [Processo(43, created=200)]
    clock.value = 1
    system, rows = collector.sample(2, 1, 1)
    assert json.loads(system["processos_adicionados"]) == [[43, 200]]
    assert json.loads(system["processos_removidos"]) == [[43, 100]]
    assert rows[1]["cpu_uma_cpu_pct"] is None
    assert not system["cpu_processos_completa"]


@pytest.mark.parametrize("failure", ["encerrado", "sem_permissao"])
def test_descendente_indisponivel(environment, failure):
    root, clock = environment
    child = root.children_list[0]
    child.alive = failure != "encerrado"
    child.denied = failure == "sem_permissao"
    system, rows = monitor.Coletor(42).sample(1, 1, 1)
    assert rows[1]["erro"] in ("NoSuchProcess", "AccessDenied")
    assert system["rss_soma_bytes"] is None


def test_principal_encerrado(environment):
    root, clock = environment
    collector = monitor.Coletor(42)
    root.alive = False
    with pytest.raises(monitor.PrincipalEncerrado):
        collector.sample(1, 1, 1)


def test_memoria_opcional_sem_permissao(environment, monkeypatch):
    root, clock = environment
    def denied(): raise psutil.AccessDenied(42)
    monkeypatch.setattr(root, "memory_full_info", denied)
    system, rows = monitor.Coletor(42, detailed=True).sample(1, 1, 1)
    assert system["rss_soma_bytes"] == 200
    assert system["uss_soma_bytes"] is None
    assert rows[0]["erro"] == "memoria_detalhada:AccessDenied"


@pytest.mark.parametrize("argument,value", [
    ("--pid", "0"), ("--usuarios", "0"), ("--repeticao", "-1"),
    ("--intervalo", "0"), ("--intervalo", "nan"), ("--duracao", "inf"),
    ("--duracao", "1"), ("--cenario", "C5"),
])
def test_parametros_invalidos(argument, value):
    with pytest.raises(SystemExit) as error:
        monitor.main(["--pid", "42", "--cenario", "C1", "--usuarios", "1", argument, value])
    assert error.value.code == 2


def options(tmp_path):
    return monitor.parser().parse_args([
        "--pid", "42", "--cenario", "C1", "--usuarios", "5", "--repeticao", "2",
        "--duracao", "2.5", "--resultados", str(tmp_path),
    ])


def test_csv_duracao_e_preservacao(environment, tmp_path, monkeypatch):
    root, clock = environment
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: setattr(clock, "value", clock.value + seconds))
    collector = monitor.Coletor(42)
    base = monitor.executar(options(tmp_path), collector)
    assert base == tmp_path / "C1/usuarios_05/repeticao_02/monitoramento_linux"
    with (base / "sistema.csv").open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        assert reader.fieldnames == monitor.SYSTEM_FIELDS
    assert len(rows) == 2
    assert float(rows[1]["tempo_relativo_s"]) == 2
    assert rows[0]["utc"].endswith("+00:00")
    assert rows[0]["cpu_soma_uma_cpu_pct"] == ""
    with (base / "processos.csv").open(encoding="utf-8", newline="") as source:
        assert len(list(csv.DictReader(source))) == 4
    data = json.loads((base / "metadados.json").read_text(encoding="utf-8"))
    assert data["estado"] == "duracao_concluida"
    assert data["amostras"] == 2
    before = (base / "sistema.csv").read_bytes()
    with pytest.raises(FileExistsError):
        monitor.executar(options(tmp_path), collector)
    assert (base / "sistema.csv").read_bytes() == before


@pytest.mark.parametrize("exception,state", [
    (KeyboardInterrupt, "ctrl_c"), (monitor.PrincipalEncerrado, "principal_encerrado"),
    (psutil.AccessDenied, "erro"),
])
def test_encerramento_seguro(environment, tmp_path, monkeypatch, exception, state):
    root, clock = environment
    def interrupt(seconds): raise exception()
    monkeypatch.setattr(monitor.time, "sleep", interrupt)
    if state == "erro":
        with pytest.raises(exception):
            monitor.executar(options(tmp_path), monitor.Coletor(42))
    else:
        monitor.executar(options(tmp_path), monitor.Coletor(42))
    base = tmp_path / "C1/usuarios_05/repeticao_02/monitoramento_linux"
    data = json.loads((base / "metadados.json").read_text(encoding="utf-8"))
    assert data["estado"] == state
    assert "fim_utc" in data
    # O fechamento permite reabrir os CSV no Windows após qualquer encerramento.
    with (base / "sistema.csv").open("a", encoding="utf-8") as output:
        output.write("")


def test_arquivo_no_caminho_de_saida(environment, tmp_path):
    (tmp_path / "C1").write_text("preservar", encoding="utf-8")
    with pytest.raises(OSError):
        monitor.executar(options(tmp_path), monitor.Coletor(42))
    assert (tmp_path / "C1").read_text(encoding="utf-8") == "preservar"


def test_diagnostico_bruto_opcional(environment, tmp_path, monkeypatch):
    root, clock = environment
    for process in [root, *root.children_list]:
        monkeypatch.setattr(process, "ppid", lambda: 1, raising=False)
        monkeypatch.setattr(process, "cmdline", lambda: ["python", "uvicorn"], raising=False)
    monkeypatch.setattr(monitor, "contadores_sistema", lambda: {
        "proc_stat_cpu_linhas": ["cpu 1 0 2 100 0 0 0 0 0 0"], "clk_tck": 100,
        "monotonic_before_s": clock.value, "monotonic_after_s": clock.value})
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: setattr(clock, "value", clock.value + seconds))
    args = options(tmp_path)
    args.diagnostico_cpu = True
    base = monitor.executar(args, monitor.Coletor(42, diagnostic=True))
    records = [json.loads(line) for line in (base / "cpu_bruto.jsonl").read_text().splitlines()]
    assert len(records) == 3
    assert records[0]["tipo"] == "baseline"
    assert records[1]["processos"][0]["pid"] == 42
    assert records[1]["processos"][0]["ppid"] == 1
    assert records[1]["processos"][0]["cpu_times_s"]["children_user"] == 999
    assert records[2]["processos"][0]["anterior"] == [0, 1]
    assert json.loads((base / "metadados.json").read_text())["diagnostico_cpu"]
