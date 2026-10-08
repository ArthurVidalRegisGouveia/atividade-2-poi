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
    return result


def validar(options, argument_parser):
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
    return [
        sys.executable, "-m", "locust", "-f", str(ROOT / "scripts/carga/locustfile.py"),
        "--headless", "--host", options.url, "--users", str(options.usuarios),
        "--spawn-rate", str(options.taxa), "--run-time", f"{seconds}s",
        "--limite", str(options.limite), "--espera", str(options.espera),
        "--reset-stats", "--csv", str(directory / phase), "--csv-full-history",
        "--only-summary", "--stop-timeout", "35", "--exit-code-on-error", "1",
    ]


def agora():
    return datetime.now(timezone.utc).isoformat()


def main(argv=None):
    argument_parser = parser()
    options = argument_parser.parse_args(argv)
    validar(options, argument_parser)
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
