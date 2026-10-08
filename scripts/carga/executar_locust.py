"""Executa apenas um cenário/repetição; não altera o provisionamento da VM."""

import argparse
import csv
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.carga.perfis import PERFIS, configurar_servidor, pedido

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = {
    "C1": {"vcpus": 1, "ram_gib": 1, "workers": 1},
    "C2": {"vcpus": 1, "ram_gib": 2, "workers": 1},
    "C3": {"vcpus": 2, "ram_gib": 1, "workers": 2},
    "C4": {"vcpus": 2, "ram_gib": 2, "workers": 2},
}


def positivo(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Informe um inteiro positivo.")
    return number


def numero(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Informe um número finito não negativo.")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--url", help="Padrão: localhost na porta da aplicação.")
    result.add_argument("--aplicacao", choices=PERFIS, default="cpu")
    result.add_argument("--tamanho-mb", type=positivo)
    result.add_argument("--operacoes", type=positivo)
    result.add_argument("--retencao-segundos", type=numero, help="Declara MEMORY_RETENCAO_SEGUNDOS na VM; não envia HTTP.")
    result.add_argument("--fsync", type=int, choices=(0, 1), help="Declara IO_FSYNC na VM; não altera servidor.")
    result.add_argument("--config-servidor", type=Path, help="JSON das variáveis do servidor; declaração não verificada remotamente.")
    result.add_argument("--cenario", choices=SCENARIOS, required=True)
    result.add_argument("--usuarios", type=positivo, required=True)
    result.add_argument("--taxa", type=numero, default=1.0, help="Usuários iniciados/s.")
    result.add_argument("--duracao", type=positivo, default=60, help="Segundos, incluindo rampa.")
    result.add_argument("--aquecimento", type=positivo, default=30, help="Segundos, incluindo rampa.")
    result.add_argument("--limite", type=positivo, default=100000)
    result.add_argument("--espera", type=numero, default=1.0)
    result.add_argument("--repeticao", type=positivo, default=1)
    result.add_argument("--somente-preparar", action="store_true", help="Registra plano sem enviar HTTP.")
    result.add_argument("--conexoes", choices=("reutilizar", "fechar"), default="reutilizar")
    result.add_argument("--registrar-worker-pid", action="store_true")
    result.add_argument("--verificacao-relogio", help="JSON de sondagens realizado antes da carga.")
    result.add_argument("--limite-latencias", type=positivo, default=100000,
                        help="Máximo de respostas registradas na medição (até 1000000).")
    return result


def validar(options, argument_parser):
    options.url = options.url or f"http://127.0.0.1:{PERFIS[options.aplicacao]['porta']}"
    if options.aplicacao == "cpu" and (options.tamanho_mb is not None or options.operacoes is not None):
        argument_parser.error("CPU aceita limite, não tamanho/operações.")
    if options.aplicacao == "memoria" and options.operacoes is not None:
        argument_parser.error("Memória não recebe operações.")
    try:
        supplied = json.loads(options.config_servidor.read_text(encoding="utf-8-sig")) if options.config_servidor else None
        config = configurar_servidor(options.aplicacao, supplied, options.retencao_segundos, options.fsync)
        endpoint, params = pedido(options)
        if options.aplicacao == "cpu" and params["limite"] > config["CPU_LIMITE_MAX"]:
            raise ValueError("Limite de primos excede teto declarado.")
        if options.aplicacao == "memoria" and not config["MEMORY_LIMITE_MIN_MB"] <= params["tamanho_mb"] <= config["MEMORY_LIMITE_MAX_MB"]:
            raise ValueError("Tamanho de memória fora dos limites declarados.")
        if options.aplicacao == "io" and (params["tamanho_mb"] > config["IO_TAMANHO_MAX_MB"] or params["operacoes"] > config["IO_OPERACOES_MAX"]):
            raise ValueError("Parâmetros I/O excedem limites declarados.")
    except (ValueError, TypeError, OSError) as error:
        argument_parser.error(str(error))
    if options.limite_latencias > 1000000:
        argument_parser.error("Limite de latências não pode exceder 1000000.")
    url = urlsplit(options.url)
    if (url.scheme not in ("http", "https") or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or url.path not in ("", "/")):
        argument_parser.error("URL deve ser uma origem HTTP(S), sem credenciais ou parâmetros.")
    if options.taxa <= 0:
        argument_parser.error("A taxa deve ser positiva.")
    ramp = math.ceil(options.usuarios / options.taxa)
    if min(options.duracao, options.aquecimento) <= ramp:
        argument_parser.error("Aquecimento e duração devem exceder usuarios/taxa.")
    return config


def comando(options, phase, directory):
    seconds = options.aquecimento if phase == "aquecimento" else options.duracao
    command = [
        sys.executable, "-m", "locust", "-f", str(ROOT / "scripts/carga/locustfile.py"),
        "--headless", "--host", options.url, "--users", str(options.usuarios),
        "--spawn-rate", str(options.taxa), "--run-time", f"{seconds}s",
        "--limite", str(options.limite), "--espera", str(options.espera),
        "--reset-stats", "--csv", str(directory / phase), "--csv-full-history",
        "--only-summary", "--stop-timeout", "35", "--exit-code-on-error", "1",
        "--conexoes", options.conexoes, "--diagnostico-saida", str(directory / f"{phase}_instrumentacao.json"),
    ]
    if options.registrar_worker_pid:
        command.append("--registrar-worker-pid")
    command.extend(["--aplicacao", options.aplicacao])
    if options.aplicacao != "cpu":
        _, params = pedido(options)
        command.extend(["--tamanho-mb", str(params["tamanho_mb"])])
        if options.aplicacao == "io":
            command.extend(["--operacoes", str(params["operacoes"])])
    if phase == "medicao":
        command.extend(["--latencias-saida", str(directory / "medicao_latencias.csv"),
                        "--limite-latencias", str(options.limite_latencias)])
    return command


def agora():
    return datetime.now(timezone.utc).isoformat()


def validar_fase(directory, phase, users, diagnostic):
    """Código zero não comprova carga válida nem encerramento sem erros."""
    errors = []
    if not isinstance(diagnostic, dict):
        diagnostic = {}
    console = (directory / f"{phase}_console.txt").read_text(encoding="utf-8", errors="replace")
    for marker in ("Traceback (most recent call last)", "Unhandled exception in greenlet",
                   "I/O operation on closed file", "unexpected state: stopping"):
        if marker.lower() in console.lower():
            errors.append(f"Erro no console: {marker}")
    try:
        with (directory / f"{phase}_stats.csv").open(encoding="utf-8-sig", newline="") as source:
            totals = [r for r in csv.DictReader(source) if r.get("Name") == "Aggregated"]
        count = float(totals[0]["Request Count"]) if len(totals) == 1 else 0
        if not math.isfinite(count) or count <= 0:
            errors.append("Fase sem requisições concluídas no resumo Locust.")
        with (directory / f"{phase}_stats_history.csv").open(encoding="utf-8-sig", newline="") as source:
            history = [r for r in csv.DictReader(source) if r.get("Name") == "Aggregated"]
        start = datetime.fromisoformat(diagnostic["usuarios_prontos_utc"])
        end = datetime.fromisoformat(diagnostic["encerramento_inicio_utc"])
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Marcos UTC inválidos")
        inside = [r for r in history if start.timestamp() < float(r["Timestamp"]) < end.timestamp()]
        if len({r["Timestamp"] for r in inside if float(r["User Count"]) == users}) < 2:
            errors.append("Sem dois snapshots de carga com a quantidade solicitada de usuários.")
        if any(float(r["User Count"]) != users for r in inside):
            errors.append("Quantidade de usuários divergiu do plano durante a janela.")
        if any(e.get("usuarios") != users for e in diagnostic.get("eventos_usuarios", [])):
            errors.append("Alteração inesperada da quantidade de usuários registrada na instrumentação.")
        if phase == "medicao":
            latency = diagnostic.get("latencias", {})
            if not latency.get("completo") or not latency.get("registros", 0):
                errors.append("Registro de latências ausente, incompleto ou vazio.")
            with (directory / "medicao_latencias.csv").open(encoding="utf-8-sig", newline="") as source:
                records = list(csv.DictReader(source))
            if len(records) != latency.get("registros"):
                errors.append("Contagem de latências diverge do arquivo registrado.")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"Artefatos de validação ausentes/inválidos: {error}")
    return errors


def main(argv=None):
    argument_parser = parser()
    options = argument_parser.parse_args(argv)
    server_config = validar(options, argument_parser)
    clock_check = None
    if options.verificacao_relogio:
        clock_check = json.loads(Path(options.verificacao_relogio).read_text(encoding="utf-8"))
        if (not isinstance(clock_check, dict) or not isinstance(clock_check.get("menor_incerteza"), dict)
                or clock_check.get("url", "").rstrip("/") != options.url.rstrip("/")):
            argument_parser.error("Verificação de relógio sem sondagem válida ou de outra URL.")
    directory = (ROOT / "experimentos/resultados/carga" / options.aplicacao / options.cenario
                 / f"usuarios_{options.usuarios:02d}" / f"repeticao_{options.repeticao:02d}")
    # Nunca sobrescreve uma repetição preexistente, inclusive um plano preparado.
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {
        "parametros": {key: str(value) if isinstance(value, Path) else value for key, value in vars(options).items()},
        "aplicacao": options.aplicacao, "endpoint": pedido(options)[0], "parametros_http": pedido(options)[1],
        "configuracao_servidor_declarada": server_config,
        "configuracao_servidor_verificada": False,
        "provisionamento_planejado": SCENARIOS[options.cenario],
        "provisionamento_verificado_automaticamente": False,
        "python": sys.version, "locust": version("locust"),
        "modelo": "fechado", "politica_espera": "fixa após cada resposta",
        "timeout_http_s": 30, "stop_timeout_s": 35,
        "duracoes_incluem_rampa": True,
        "aquecimento_em_processo_separado": True,
        "entrada_interativa": "desabilitada (stdin pipe fechado; NUL pode ser tty no Windows)",
        "criado_utc": agora(), "fases": [],
        "verificacao_relogio": clock_check,
    }
    path = directory / "parametros.json"

    def salvar():
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    salvar()
    for phase in ("aquecimento", "medicao"):
        command = comando(options, phase, directory)
        # Registra comandos portáveis, sem caminhos absolutos pessoais.
        relative_command = [item.replace(str(ROOT), ".") for item in command]
        relative_command[0] = "python"
        entry = {"fase": phase, "comando": relative_command, "estado": "planejado"}
        metadata["fases"].append(entry)
        salvar()
        if options.somente_preparar:
            print(subprocess.list2cmdline(relative_command))
            continue
        entry.update(estado="executando", inicio_utc=agora())
        salvar()
        start = time.perf_counter()
        try:
            with (directory / f"{phase}_console.txt").open("x", encoding="utf-8") as output:
                completed = subprocess.run(command, cwd=ROOT, stdout=output,
                                           stderr=subprocess.STDOUT, stdin=subprocess.PIPE, check=False)
            entry.update(codigo_saida=completed.returncode)
            diagnostic = directory / f"{phase}_instrumentacao.json"
            try:
                entry["instrumentacao"] = json.loads(diagnostic.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                entry["instrumentacao"] = {}
            issues = validar_fase(directory, phase, options.usuarios, entry["instrumentacao"])
            entry.update(estado="falha" if completed.returncode or issues else "concluido",
                         erros_validacao=issues)
        except (OSError, KeyboardInterrupt) as error:
            entry.update(estado="interrompido", erro=type(error).__name__)
            raise
        finally:
            entry.update(fim_utc=agora(), tempo_parede_s=time.perf_counter() - start)
            salvar()
        if completed.returncode:
            return completed.returncode
        if issues:
            print(f"Fase {phase} inválida: {'; '.join(issues)}", file=sys.stderr)
            return 2
    print(f"Resultados: {directory.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
