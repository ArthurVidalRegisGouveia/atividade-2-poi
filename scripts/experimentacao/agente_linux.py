"""Auxiliar SSH: audita servidores e controla somente monitores que iniciou."""

import ast
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.carga.perfis import PADROES_SERVIDOR, PERFIS, configurar_servidor


def gravar(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pasta(token):
    if str(uuid.UUID(token)) != token:
        raise ValueError("Token inválido.")
    return ROOT / ".temp/orquestracao" / token


def testar_escrita(directory):
    directory.mkdir(parents=True, exist_ok=True)
    # Remove apenas a sonda recém-criada pelo próprio helper.
    path = directory / (".sonda_" + uuid.uuid4().hex)
    with path.open("x") as source:
        source.write("ok")
    path.unlink()


def auditar(app):
    module = {"cpu": "cpu_bound", "memoria": "memory_bound", "io": "io_bound"}[app]
    code = ROOT / "apps" / module / "main.py"
    source = code.read_text(encoding="utf-8")
    defaults = {}
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "os"
                and node.func.attr == "getenv" and len(node.args) == 2
                and all(isinstance(arg, ast.Constant) for arg in node.args)):
            defaults[node.args[0].value] = node.args[1].value
    for key, expected in PADROES_SERVIDOR[app].items():
        if str(defaults.get(key)) != str(expected):
            raise ValueError(f"Padrão de {key} não corresponde ao código auditado.")
    listeners = {conn.pid for conn in psutil.net_connections(kind="tcp")
                 if conn.status == psutil.CONN_LISTEN and conn.laddr.port == PERFIS[app]["porta"] and conn.pid}
    roots = {}
    for pid in listeners:
        process = psutil.Process(pid)
        for candidate in [process, *process.parents()]:
            command = candidate.cmdline()
            if not any(Path(part).name in ("uvicorn", "uvicorn.exe") for part in command):
                continue
            if f"apps.{module}.main:app" in command:
                roots[candidate.pid] = candidate
                break
            if "scripts.monitoramento.servidor_experimental:criar_app" in command:
                if candidate.environ().get("POI_APLICACAO", "cpu") == app:
                    roots[candidate.pid] = candidate
                break
    if len(roots) != 1:
        raise ValueError(f"Porta {PERFIS[app]['porta']}: não há um único servidor principal comprovado para {app}.")
    root = next(iter(roots.values()))
    command = root.cmdline()
    workers = [child for child in root.children(recursive=True)
               if "--multiprocessing-fork" in child.cmdline() and child.status() != psutil.STATUS_ZOMBIE]
    if not workers:
        # Um supervisor configurado para vários workers não é um worker único.
        if "--workers" in command and int(command[command.index("--workers") + 1]) > 1:
            raise ValueError("Workers configurados, mas processos workers não encontrados.")
        workers = [root]
    # net_connections global pode informar somente um PID para o inode compartilhado.
    # Confere separadamente os descritores de cada worker identificado na árvore.
    if any(not any(conn.status == psutil.CONN_LISTEN and conn.laddr.port == PERFIS[app]["porta"]
                   for conn in worker.net_connections(kind="tcp")) for worker in workers):
        raise ValueError("Não foi possível comprovar sockets de escuta dos workers.")
    observations, configs = [], []
    for process in {p.pid: p for p in [root, *workers]}.values():
        env = process.environ()
        supplied = {key: env[key] for key in PADROES_SERVIDOR[app] if key in env}
        config = configurar_servidor(app, supplied)
        if code.stat().st_mtime > process.create_time() + 1:
            raise ValueError("Código foi alterado após iniciar o servidor; reinicie antes de auditar.")
        if "scripts.monitoramento.servidor_experimental:criar_app" in command:
            wrapper = ROOT / "scripts/monitoramento/servidor_experimental.py"
            if wrapper.stat().st_mtime > process.create_time() + 1:
                raise ValueError("Wrapper alterado após iniciar o servidor.")
            diagnostic = env.get("POI_DIAGNOSTICO") == "1" or (app == "cpu" and env.get("CPU_DIAGNOSTICO") == "1")
        else:
            diagnostic = app == "cpu" and env.get("CPU_DIAGNOSTICO") == "1"
        if not diagnostic:
            raise ValueError("Cabeçalhos de PID/relógio não estão habilitados no processo.")
        observations.append(dict(pid=process.pid, criado_epoch_s=process.create_time(), ppid=process.ppid(),
                                 comando=process.cmdline(), variaveis_relevantes=supplied,
                                 defaults_utilizados={key: defaults[key] for key in config if key not in supplied}))
        configs.append(config)
    if any(config != configs[0] for config in configs):
        raise ValueError("Configuração diverge entre gerenciador e workers.")
    config = configs[0]
    io_directory = None
    if app == "io":
        io_directory = Path(config["IO_DIRETORIO_TEMP"]).expanduser()
        if not io_directory.is_absolute():
            io_directory = ROOT / io_directory
        io_directory = io_directory.resolve()
        if not io_directory.is_dir() or io_directory == Path("/"):
            raise ValueError("Diretório I/O não está disponível ou é raiz.")
        testar_escrita(io_directory)
    return dict(aplicacao=app, pid_principal=root.pid, workers=len(workers), processos=observations,
                configuracao_verificada=config, defaults_auditados=defaults,
                codigo_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                diretorio_io=str(io_directory) if io_directory else None,
                espaco_io_livre_bytes=psutil.disk_usage(str(io_directory)).free if io_directory else None)


def audit(request):
    testar_escrita(ROOT / "experimentos/resultados/carga")
    if (ROOT / ".temp/poi_experimentos.lock").exists():
        raise ValueError("Há uma reserva experimental remota; confira a execução anterior.")
    for process in psutil.process_iter(["cmdline"]):
        if any(part.endswith("monitorar_linux.py") for part in (process.info["cmdline"] or [])):
            raise ValueError("Há monitor Linux ativo; não sobrepor execuções.")
    servers = [auditar(app) for app in request["aplicacoes"]]
    return dict(cpus=psutil.cpu_count(logical=True), ram_total_bytes=psutil.virtual_memory().total,
                servidores=servers, resultados_escrita=True)


def monitor_path(job):
    return ROOT / "experimentos/resultados/carga" / job["aplicacao"] / job["cenario"] / f"usuarios_{job['usuarios']:02d}" / f"repeticao_{job['repeticao']:02d}" / "monitoramento_linux"


def start(request):
    token, job = request["token"], request["job"]
    base = pasta(token)
    server = psutil.Process(request["pid"])
    if not server.is_running() or server.create_time() != request["servidor_criado_epoch_s"]:
        raise ValueError("Servidor principal mudou após auditoria.")
    if monitor_path(job).exists():
        raise ValueError("Monitoramento remoto já existe; nova tentativa necessária.")
    base.mkdir(parents=True, exist_ok=False)
    lock = ROOT / ".temp/poi_experimentos.lock"
    with lock.open("x") as source:
        source.write(token)
    command = [sys.executable, "-u", str(ROOT / "scripts/monitoramento/monitorar_linux.py"),
               "--pid", str(request["pid"]), "--aplicacao", job["aplicacao"], "--cenario", job["cenario"],
               "--usuarios", str(job["usuarios"]), "--repeticao", str(job["repeticao"]),
               "--intervalo", "1", "--duracao", str(request["duracao"]), "--diagnostico-cpu",
               "--condicoes", "Orquestrador; token=" + token]
    if job["aplicacao"] in ("memoria", "io"):
        command.append("--memoria-detalhada")
    if job["aplicacao"] == "io":
        command.append("--discos")
    try:
        with (base / "monitor_console.txt").open("x") as output:
            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        identity = psutil.Process(process.pid).create_time()
        record = dict(token=token, pid=process.pid, criado_epoch_s=identity, comando=command,
                      monitoramento=str(monitor_path(job)), job=job)
        gravar(base / "controle.json", record)
        return record
    except Exception:
        # Sem journal não há carga autorizada; reserva permanece para inspeção manual.
        raise


def status(request):
    base = pasta(request["token"])
    record = json.loads((base / "controle.json").read_text(encoding="utf-8"))
    alive = False
    try:
        process = psutil.Process(record["pid"])
        if process.create_time() == record["criado_epoch_s"]:
            if process.status() != psutil.STATUS_ZOMBIE and process.cmdline() != record["comando"]:
                raise ValueError("Comando do processo mudou; controle e liberação da reserva recusados.")
            alive = process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pass
    path = Path(record["monitoramento"])
    try:
        metadata = json.loads((path / "metadados.json").read_text()) if (path / "metadados.json").exists() else {}
    except json.JSONDecodeError:
        metadata = {}  # Arquivo do monitor pode estar no meio de uma atualização.
    ready = False
    if (path / "sistema.csv").is_file():
        with (path / "sistema.csv").open() as source:
            ready = next(source, None) is not None and next(source, None) is not None
    if not alive:
        lock = ROOT / ".temp/poi_experimentos.lock"
        if lock.exists() and lock.read_text() == request["token"]:
            lock.unlink()  # Somente reserva deste monitor.
    return dict(vivo=alive, pronto=alive and ready and metadata.get("estado") == "executando",
                metadados=metadata, controle=record)


def stop(request):
    state = status(request)
    if state["vivo"]:
        # status comprovou PID, criação e comando antes de enviar o sinal.
        os.kill(state["controle"]["pid"], signal.SIGINT)
    return state


def main():
    request = json.load(sys.stdin)
    if request.get("acao") == "auditar":
        response = audit(request)
    elif request.get("acao") in ("iniciar", "estado", "encerrar"):
        response = {"iniciar": start, "estado": status, "encerrar": stop}[request["acao"]](request)
    else:
        raise ValueError("Ação desconhecida.")
    print(json.dumps(response))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"erro": f"{type(error).__name__}: {error}"}))
        sys.exit(1)
