"""Planeja por padrão; execução explícita e sequencial com reservas exclusivas."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
import json
import hashlib
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts.carga.executar_locust import SCENARIOS
from scripts.carga.perfis import PERFIS

DEMANDAS = {"cpu": [1, 2, 5, 10], "memoria": [1, 2, 3], "io": [1, 2]}


class Falha(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def salvar(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--planejar", action="store_true")
    mode.add_argument("--validar-ambiente", action="store_true")
    mode.add_argument("--executar", action="store_true")
    p.add_argument("--id-execucao", required=True, help="Identificador novo; --retomar permite continuar o mesmo índice.")
    p.add_argument("--cenario", choices=SCENARIOS)
    p.add_argument("--aplicacao", choices=PERFIS)
    p.add_argument("--usuarios", type=int)
    p.add_argument("--repeticao", type=int, choices=(1, 2, 3), help="Repetição lógica, não o número reservado no disco.")
    p.add_argument("--tentativa", type=int, default=1, choices=range(1, 100))
    p.add_argument("--base-repeticao", type=int, default=1000)
    p.add_argument("--retomar", action="store_true")
    p.add_argument("--confirmar-provisionamento", choices=SCENARIOS)
    p.add_argument("--ssh", default="osboxes@127.0.0.1")
    p.add_argument("--porta-ssh", type=int, default=2222)
    p.add_argument("--raiz-vm", default="/home/osboxes/atividade-2-poi")
    p.add_argument("--timeout-ssh", type=float, default=30)
    p.add_argument("--timeout-locust", type=float, default=210)
    p.add_argument("--timeout-prontidao", type=float, default=30)
    p.add_argument("--timeout-transferencia", type=float, default=120)
    p.add_argument("--duracao-monitor", type=float, default=200)
    p.add_argument("--intervalo-consulta", type=float, default=1)
    return p


def validar_opcoes(o, p):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", o.id_execucao):
        p.error("Identificador deve ter até 64 caracteres alfanuméricos, _ ou -.")
    if o.base_repeticao < 1000 or o.base_repeticao % 1000:
        p.error("Base reservada deve ser múltiplo de 1000, a partir de 1000.")
    if not 1 <= o.porta_ssh <= 65535 or not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", o.ssh):
        p.error("SSH deve ser usuário@host, sem opções ou credenciais embutidas.")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", o.raiz_vm) or ".." in o.raiz_vm.split("/"):
        p.error("Raiz VM precisa ser um caminho absoluto Linux.")
    import math
    for key in ("timeout_ssh", "timeout_locust", "timeout_prontidao", "timeout_transferencia", "duracao_monitor", "intervalo_consulta"):
        if not math.isfinite(getattr(o, key)) or getattr(o, key) <= 0:
            p.error(f"{key} deve ser finito e positivo.")
    if o.duracao_monitor < 180:
        p.error("Monitor deve cobrir 30 + 60 + duas drenagens de até 35 s e margem; mínimo 180 s.")
    if (o.executar or o.validar_ambiente) and not o.cenario:
        p.error("Validação/execução exige um único --cenario; provisionamento é manual.")
    if o.executar and o.confirmar_provisionamento != o.cenario:
        p.error("Confirme o cenário efetivamente provisionado com --confirmar-provisionamento.")


def matriz(o):
    jobs = []
    for scenario in ([o.cenario] if o.cenario else SCENARIOS):
        for app in ([o.aplicacao] if o.aplicacao else DEMANDAS):
            for users in DEMANDAS[app]:
                if o.usuarios is not None and users != o.usuarios:
                    continue
                for repeat in ([o.repeticao] if o.repeticao else (1, 2, 3)):
                    number = o.base_repeticao + (o.tentativa - 1) * 10 + repeat
                    relative = f"experimentos/resultados/carga/{app}/{scenario}/usuarios_{users:02d}/repeticao_{number:02d}"
                    jobs.append(dict(aplicacao=app, cenario=scenario, usuarios=users, repeticao=number,
                                     repeticao_logica=repeat, tentativa=o.tentativa, caminho=relative,
                                     aquecimento_s=30, medicao_configurada_s=60, espera_s=0, conexoes="fechar",
                                     taxa=users, parametros_http={"limite": 250000} if app == "cpu" else
                                     {"tamanho_mb": 50} if app == "memoria" else {"tamanho_mb": 10, "operacoes": 1}))
    if not jobs:
        raise Falha("Filtros não selecionam nenhuma combinação da matriz.")
    return jobs


@contextmanager
def reserva_local(root):
    path = root / ".temp/poi_orquestrador.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    try:
        with path.open("x") as source:
            source.write(token)
    except FileExistsError as error:
        raise Falha("Outro orquestrador ou reserva interrompida existe; confira antes de remover manualmente.") from error
    try:
        yield
    finally:
        if path.exists() and path.read_text() == token:
            path.unlink()  # Reserva criada por esta execução; nenhum resultado removido.


class Operacoes:
    def __init__(self, options):
        self.o = options
        self.root = ROOT
        self.events = []

    def run(self, command, timeout, input=None):
        event = dict(comando=command, inicio_utc=utc())
        if input is not None:
            event["entrada_json"] = json.loads(input)
        self.events.append(event)
        try:
            result = subprocess.run(command, input=input, capture_output=True, text=True, timeout=timeout, check=False)
            event.update(codigo_saida=result.returncode, fim_utc=utc())
            if result.returncode:
                raise Falha(f"Comando retornou {result.returncode}: {(result.stderr or result.stdout)[-1500:]}")
            return result.stdout
        except subprocess.TimeoutExpired as error:
            event.update(estado="timeout", fim_utc=utc())
            raise Falha(f"Timeout do comando: {command[0]}") from error

    def remoto(self, request):
        command = " ".join(shlex.quote(part) for part in [self.o.raiz_vm + "/.venv/bin/python",
                   self.o.raiz_vm + "/scripts/experimentacao/agente_linux.py"])
        raw = self.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", str(self.o.porta_ssh),
                        self.o.ssh, command], self.o.timeout_ssh, json.dumps(request))
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise Falha("Resposta SSH não é JSON; confira saída/banner e implantação do helper.") from error
        if "erro" in data:
            raise Falha(data["erro"])
        return data

    def health(self, app):
        with urlopen(f"http://127.0.0.1:{PERFIS[app]['porta']}/health", timeout=5) as response:
            if response.status != 200 or json.load(response) != {"status": "ok"}:
                raise Falha("Endpoint /health incompatível.")
            try:
                return int(response.headers["X-Worker-PID"])
            except (KeyError, TypeError, ValueError) as error:
                raise Falha("/health não forneceu X-Worker-PID válido; configure diagnóstico experimental.") from error

    def sondar(self, app, path):
        self.run([sys.executable, "-B", str(self.root / "scripts/monitoramento/verificar_relogios.py"),
                  "--url", f"http://127.0.0.1:{PERFIS[app]['porta']}", "--saida", str(path)], self.o.timeout_ssh)

    def local(self, command, logfile, timeout):
        event = dict(comando=command, inicio_utc=utc())
        self.events.append(event)
        with logfile.open("x", encoding="utf-8") as output:
            env = dict(os.environ, TEMP=str(self.root / ".temp"), TMP=str(self.root / ".temp"))
            process = subprocess.Popen(command, cwd=self.root, stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.PIPE,
                                       env=env,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                                       start_new_session=os.name != "nt")
            # NUL/DEVNULL pode ser tty no Windows; pipe fechado desativa os atalhos.
            process.stdin.close()
            import psutil
            try:
                process.poi_identity = psutil.Process(process.pid).create_time()
            except psutil.NoSuchProcess:
                process.poi_identity = None
            try:
                code = process.wait(timeout=timeout)
                event.update(codigo_saida=code, fim_utc=utc())
                if code:
                    raise Falha(f"Locust retornou {code}; confira {logfile}.")
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                self.parar_local(process)
                event.update(estado="interrompido_ou_timeout", fim_utc=utc())
                raise

    @staticmethod
    def parar_local(process):
        if process.poll() is not None:
            return
        import psutil
        root = psutil.Process(process.pid)
        if root.create_time() != process.poi_identity:
            raise Falha("PID local mudou; encerramento recusado para proteger outros processos.")
        # Captura somente a árvore do Popen que acabamos de criar.
        targets = [root, *root.children(recursive=True)]
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
        except (OSError, ValueError):
            pass  # Sem console Windows: fallback restrito à árvore comprovada.
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for target in reversed(targets):
            try:
                if target.is_running():
                    target.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(targets, timeout=5)
        for target in alive:
            target.kill()
        process.wait(timeout=5)

    def copiar(self, remote, target):
        if target.exists():
            raise Falha("Destino SCP já existe; não será sobrescrito.")
        self.run(["scp", "-o", "BatchMode=yes", "-P", str(self.o.porta_ssh), "-r",
                  self.o.ssh + ":" + remote, str(target)], self.o.timeout_transferencia)

    def conferir_host(self):
        import psutil
        try:
            version("locust")
        except ModuleNotFoundError as error:
            raise Falha("Instale requirements-carga.txt no ambiente virtual local.") from error
        directory = self.root / "experimentos/resultados/carga"
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / (".sonda_" + uuid.uuid4().hex)
        with probe.open("x") as source:
            source.write("ok")
        probe.unlink()
        for process in psutil.process_iter(["pid", "cmdline"]):
            if process.pid == os.getpid():
                continue
            command = process.info["cmdline"] or []
            if any("locustfile.py" in part or part == "locust" for part in command):
                raise Falha("Há gerador Locust ativo no host; não iniciar carga simultânea.")


def verificar_ambiente(ops, jobs):
    ops.conferir_host()
    apps = sorted({job["aplicacao"] for job in jobs})
    data = ops.remoto(dict(acao="auditar", aplicacoes=apps))
    expected = SCENARIOS[jobs[0]["cenario"]]
    if data["cpus"] != expected["vcpus"]:
        raise Falha("vCPUs observadas divergem do cenário.")
    ram = data["ram_total_bytes"] / (1024 ** 3)
    if not .85 * expected["ram_gib"] <= ram <= 1.05 * expected["ram_gib"]:
        raise Falha("MemTotal observado diverge da RAM planejada (tolerância de reserva do kernel).")
    for server in data["servidores"]:
        app, config = server["aplicacao"], server["configuracao_verificada"]
        if server["workers"] != expected["workers"]:
            raise Falha("Quantidade de workers observados diverge do cenário.")
        if app == "memoria" and config["MEMORY_RETENCAO_SEGUNDOS"] != 1:
            raise Falha("MEMORY_RETENCAO_SEGUNDOS=1 não foi confirmado.")
        if app == "io" and config["IO_FSYNC"] != 1:
            raise Falha("IO_FSYNC=1 não foi confirmado.")
        if app == "cpu" and config["CPU_LIMITE_MAX"] < 250000:
            raise Falha("Limite CPU inferior ao da matriz.")
        if app == "memoria" and not config["MEMORY_LIMITE_MIN_MB"] <= 50 <= config["MEMORY_LIMITE_MAX_MB"]:
            raise Falha("Tamanho de memória da matriz fora dos limites efetivos.")
        if app == "io" and (config["IO_TAMANHO_MAX_MB"] < 10 or config["IO_OPERACOES_MAX"] < 1 or server["espaco_io_livre_bytes"] < 256 * 1024 ** 2):
            raise Falha("Limites ou espaço livre I/O insuficientes para a matriz (mínimo conservador 256 MiB).")
        pid = ops.health(app)
        if pid not in {process["pid"] for process in server["processos"]}:
            raise Falha("PID do endpoint não pertence à árvore auditada.")
    if {server["aplicacao"] for server in data["servidores"]} != set(apps):
        raise Falha("Auditoria incompleta das aplicações.")
    return data


def aguardar(ops, token, ready):
    timeout = ops.o.timeout_prontidao if ready else ops.o.duracao_monitor + ops.o.timeout_prontidao
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = ops.remoto(dict(acao="estado", token=token))
        if ready and state["pronto"]:
            return state
        if not state["vivo"]:
            if ready or state["metadados"].get("estado") != "duracao_concluida":
                raise Falha("Monitor encerrou sem completar a coleta.")
            return state
        time.sleep(ops.o.intervalo_consulta)  # Consulta de prontidão, não simulação de carga.
    raise Falha("Timeout aguardando monitor.")


def comando_locust(ops, job, before, config_path):
    command = [sys.executable, "-B", str(ops.root / "scripts/carga/executar_locust.py"),
               "--aplicacao", job["aplicacao"], "--cenario", job["cenario"], "--usuarios", str(job["usuarios"]),
               "--repeticao", str(job["repeticao"]), "--taxa", str(job["usuarios"]),
               "--aquecimento", "30", "--duracao", "60", "--espera", "0", "--conexoes", "fechar",
               "--registrar-worker-pid", "--verificacao-relogio", str(before), "--config-servidor", str(config_path)]
    for key, value in job["parametros_http"].items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    return command


def indice(directory):
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*/manifesto.json"))]
    salvar(directory / "indice.json", [{"job": row["job"], "estado": row["estado"], "manifesto": row["manifesto"]} for row in records])
    general = []
    for path in sorted(directory.parent.glob("*/indice.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            general.append(dict(campanha=path.parent.name, **row))
    salvar(directory.parent / "indice_geral.json", general)


def conferir_relogios(before, after):
    a = json.loads(before.read_text(encoding="utf-8"))["menor_incerteza"]
    b = json.loads(after.read_text(encoding="utf-8"))["menor_incerteza"]
    if (a["offset_servidor_menos_cliente_max_s"] < b["offset_servidor_menos_cliente_min_s"]
            or b["offset_servidor_menos_cliente_max_s"] < a["offset_servidor_menos_cliente_min_s"]):
        raise Falha("Faixas de offset antes/depois não se sobrepõem; coleta não será tratada como definitiva.")


def conferir_cobertura(target, metadata, before):
    import csv
    from scripts.analise.consolidar_resultados import instante
    from datetime import timedelta
    shift = -json.loads(before.read_text(encoding="utf-8"))["menor_incerteza"]["offset_estimado_s"]
    measurement = next(phase for phase in metadata["fases"] if phase["fase"] == "medicao")
    warm = next(phase for phase in metadata["fases"] if phase["fase"] == "aquecimento")
    with (target / "monitoramento_linux/sistema.csv").open(encoding="utf-8", newline="") as source:
        stamps = [instante(row["utc"]) + timedelta(seconds=shift) for row in csv.DictReader(source)]
    if (not stamps or min(stamps) > instante(warm["instrumentacao"]["usuarios_prontos_utc"])
            or max(stamps) < instante(measurement["instrumentacao"]["encerramento_inicio_utc"])):
        raise Falha("Amostras do monitor não cobrem aquecimento e janela de carga após correção de horário.")


def executar_job(ops, job, manifest, path, campaign):
    token = str(uuid.uuid4())
    target = ops.root / job["caminho"]
    monitor_started = False
    manifest.update(estado="em andamento", inicio_utc=utc(), token_monitor=token, comandos=ops.events)
    salvar(path, manifest)
    indice(campaign)
    try:
        if target.exists():
            raise Falha("Repetição já existe: use uma nova tentativa; nenhuma sobrescrita permitida.")
        audit = verificar_ambiente(ops, [job])
        manifest["ambiente_verificado"] = audit
        server = audit["servidores"][0]
        config_path = path.parent / "servidor_verificado.json"
        with config_path.open("x", encoding="utf-8") as source:
            json.dump(server["configuracao_verificada"], source)
        before, after = path.parent / "relogio_antes.json", path.parent / "relogio_depois.json"
        ops.sondar(job["aplicacao"], before)
        # Marcar antes do SSH: resposta perdida após Popen exige recuperar o token.
        monitor_started = True
        created = next(process["criado_epoch_s"] for process in server["processos"] if process["pid"] == server["pid_principal"])
        control = ops.remoto(dict(acao="iniciar", token=token, job=job, pid=server["pid_principal"],
                                 servidor_criado_epoch_s=created, duracao=ops.o.duracao_monitor))
        manifest["monitor"] = control
        aguardar(ops, token, ready=True)
        command = comando_locust(ops, job, before, config_path)
        try:
            ops.local(command, path.parent / "locust_console.txt", ops.o.timeout_locust)
        finally:
            # Também preserva sondagem após falha Locust, sem prosseguir a matriz.
            ops.sondar(job["aplicacao"], after)
        finished = aguardar(ops, token, ready=False)
        monitor_started = False
        if any(finished["metadados"].get(key) != job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")):
            raise Falha("Identificação do monitor diverge da execução.")
        ops.copiar(control["monitoramento"], target / "monitoramento_linux")
        # As sondagens ficam também junto da repetição, exclusivamente em arquivos novos.
        for original in (before, after):
            with (target / original.name).open("xb") as source:
                source.write(original.read_bytes())
        metadata_path = target / "parametros.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if any(metadata["parametros"].get(key) != job[key] for key in ("aplicacao", "cenario", "usuarios", "repeticao")):
            raise Falha("Metadados Locust não correspondem ao job.")
        metadata.update(configuracao_servidor_verificada=True, verificacao_ambiente=audit,
                        verificacao_relogio_posterior=json.loads(after.read_text(encoding="utf-8")))
        salvar(metadata_path, metadata)  # Apenas metadados desta tentativa recém-criada.
        conferir_relogios(before, after)
        conferir_cobertura(target, metadata, before)
        output = path.parent / "analise"
        ops.run([sys.executable, "-B", str(ops.root / "scripts/analise/consolidar_resultados.py"),
                 str(target), "--saida", str(output)], ops.o.timeout_transferencia)
        import csv
        with (output / "consolidado.csv").open(encoding="utf-8", newline="") as source:
            row = next(csv.DictReader(source))
        if not row.get("p95_janela_ms") or not row.get("latencias_janela_n") or float(row.get("req_janela") or 0) <= 0 or int(row.get("amostras_sistema") or 0) <= 0:
            raise Falha("Consolidado não contém latências e recursos válidos; execução permanece incompleta.")
        artifacts = [output / "consolidado.csv", output / "resumo.txt", metadata_path,
                     target / "monitoramento_linux/metadados.json", target / "medicao_latencias.csv", before, after]
        manifest["artefatos_sha256"] = {str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in artifacts}
        manifest.update(estado="concluída", avisos=row.get("avisos", ""), analise=str(output), resultados=str(target))
    except KeyboardInterrupt:
        manifest.update(estado="interrompida", erro="Ctrl+C")
        raise
    except Exception as error:
        manifest.update(estado="falha", erro=f"{type(error).__name__}: {error}")
        raise
    finally:
        if monitor_started:
            try:
                ops.remoto(dict(acao="encerrar", token=token))
                # Não deixa uma reserva remota ativa em retomada normal.
                deadline = time.monotonic() + ops.o.timeout_prontidao
                while time.monotonic() < deadline:
                    if not ops.remoto(dict(acao="estado", token=token))["vivo"]:
                        break
                    time.sleep(ops.o.intervalo_consulta)
                else:
                    raise Falha("Monitor não encerrou; reserva remota requer inspeção manual.")
            except Exception as error:
                manifest["aviso_encerramento"] = str(error)
        manifest.update(fim_utc=utc(), comandos=ops.events)
        salvar(path, manifest)
        indice(campaign)


def main(argv=None):
    p = parser()
    o = p.parse_args(argv)
    validar_opcoes(o, p)
    try:
        jobs = matriz(o)
        campaign = ROOT / "experimentos/resultados/orquestracao" / o.id_execucao
        if campaign.exists() and not o.retomar:
            raise Falha("ID já existe: --retomar para continuar ou novo ID para novo plano.")
        if o.retomar and not campaign.exists():
            raise Falha("ID de retomada não existe.")
        if o.executar or o.validar_ambiente:
            import shutil
            if not shutil.which("ssh") or not shutil.which("scp"):
                raise Falha("OpenSSH ssh/scp não encontrado no PATH.")
        campaign.mkdir(parents=True, exist_ok=True)
        with reserva_local(ROOT):
            if o.validar_ambiente:
                ops = Operacoes(o)
                audit = verificar_ambiente(ops, jobs)
                path = campaign / ("validacao_" + uuid.uuid4().hex + ".json")
                salvar(path, dict(utc=utc(), ambiente=audit, comandos=ops.events))
                print(f"Ambiente validado: {path}")
                return 0
            for job in jobs:
                key = f"{job['aplicacao']}_{job['cenario']}_u{job['usuarios']:02d}_r{job['repeticao']}"
                path = campaign / key / "manifesto.json"
                if path.exists():
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    if manifest["job"] != job:
                        raise Falha("Plano anterior difere dos parâmetros atuais.")
                    if manifest["estado"] == "concluída":
                        artifacts = manifest.get("artefatos_sha256", {})
                        if not artifacts or any(not Path(file).is_file() or hashlib.sha256(Path(file).read_bytes()).hexdigest() != digest for file, digest in artifacts.items()):
                            raise Falha("Conclusão registrada sem análise disponível; confira manualmente.")
                        continue
                    if manifest["estado"] != "planejada":
                        raise Falha("Tentativa incompleta: preserve os arquivos e use --tentativa maior.")
                else:
                    if (ROOT / job["caminho"]).exists():
                        raise Falha("Colisão de repetição: escolha nova tentativa/base.")
                    path.parent.mkdir(parents=True, exist_ok=False)
                    manifest = dict(job=job, estado="planejada", criado_utc=utc(), manifesto=str(path),
                                    vm_nome_declarado="POI-Ubuntu-Server", provisionamento_confirmado=o.confirmar_provisionamento,
                                    comandos_planejados={"locust": comando_locust(Operacoes(o), job,
                                        path.parent / "relogio_antes.json", path.parent / "servidor_verificado.json")})
                    salvar(path, manifest)
                indice(campaign)
                if o.executar:
                    executar_job(Operacoes(o), job, manifest, path, campaign)
                else:
                    print(f"PLANO {key}: {job['parametros_http']} -> {job['caminho']}")
            print(f"Índice: {campaign / 'indice.json'}")
            return 0
    except (Falha, OSError, ValueError, subprocess.TimeoutExpired) as error:
        p.exit(1, f"Orquestração interrompida: {error}\n")
    except KeyboardInterrupt:
        p.exit(130, "Interrompida; arquivos preservados. Use nova tentativa para coletas incompletas.\n")


if __name__ == "__main__":
    raise SystemExit(main())
