"""Executa apenas um cenário/repetição; não altera o provisionamento da VM."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

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
    result.add_argument("--url", default="http://127.0.0.1:8001")
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
    if phase == "medicao":
        command.extend(["--latencias-saida", str(directory / "medicao_latencias.csv"),
                        "--limite-latencias", str(options.limite_latencias)])
    return command


def agora():
    return datetime.now(timezone.utc).isoformat()


def main(argv=None):
    argument_parser = parser()
    options = argument_parser.parse_args(argv)
    validar(options, argument_parser)
    clock_check = None
    if options.verificacao_relogio:
        clock_check = json.loads(Path(options.verificacao_relogio).read_text(encoding="utf-8"))
        if (not isinstance(clock_check, dict) or not isinstance(clock_check.get("menor_incerteza"), dict)
                or clock_check.get("url", "").rstrip("/") != options.url.rstrip("/")):
            argument_parser.error("Verificação de relógio sem sondagem válida ou de outra URL.")
    directory = (ROOT / "experimentos/resultados/carga" / options.cenario
                 / f"usuarios_{options.usuarios:02d}" / f"repeticao_{options.repeticao:02d}")
    # Nunca sobrescreve uma repetição preexistente, inclusive um plano preparado.
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {
        "parametros": vars(options), "provisionamento_planejado": SCENARIOS[options.cenario],
        "provisionamento_verificado_automaticamente": False,
        "python": sys.version, "locust": version("locust"),
        "modelo": "fechado", "politica_espera": "fixa após cada resposta",
        "timeout_http_s": 30, "stop_timeout_s": 35,
        "duracoes_incluem_rampa": True,
        "aquecimento_em_processo_separado": True,
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
                                           stderr=subprocess.STDOUT, check=False)
            entry.update(estado="concluido", codigo_saida=completed.returncode)
            diagnostic = directory / f"{phase}_instrumentacao.json"
            if diagnostic.is_file():
                entry["instrumentacao"] = json.loads(diagnostic.read_text(encoding="utf-8"))
            else:
                entry["aviso_instrumentacao"] = "Marcos diretos ausentes; compatibilidade com console mantida."
        except (OSError, KeyboardInterrupt) as error:
            entry.update(estado="interrompido", erro=type(error).__name__)
            raise
        finally:
            entry.update(fim_utc=agora(), tempo_parede_s=time.perf_counter() - start)
            salvar()
        if completed.returncode:
            return completed.returncode
    print(f"Resultados: {directory.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
