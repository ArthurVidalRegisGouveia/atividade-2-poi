"""Carga fechada e determinística: uma requisição por usuário a cada tarefa."""

import argparse
import math
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from scripts.carga.latencias import RegistroLatencias

from locust import HttpUser, events, task


def inteiro_positivo(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Informe um inteiro positivo.")
    return number


def espera_valida(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("A espera deve ser finita e não negativa.")
    return number


@events.init_command_line_parser.add_listener
def argumentos(parser, **kwargs):
    parser.add_argument("--limite", type=inteiro_positivo, default=100000,
                        help="Mesmo limite inclusivo em todos os cenários.")
    parser.add_argument("--espera", type=espera_valida, default=1.0,
                        help="Segundos fixos após cada resposta; 0 = sem pausa.")
    parser.add_argument("--conexoes", choices=("reutilizar", "fechar"), default="reutilizar")
    parser.add_argument("--registrar-worker-pid", action="store_true")
    parser.add_argument("--diagnostico-saida", help="JSON de marcos/contagem; executor define por fase.")
    parser.add_argument("--latencias-saida", help="CSV exclusivo da medição; sem rampa ou drenagem.")
    parser.add_argument("--limite-latencias", type=inteiro_positivo, default=100000)


@events.init.add_listener
def instrumentar(environment, **kwargs):
    options = environment.parsed_options
    path = getattr(options, "diagnostico_saida", None)
    if path and Path(path).exists():
        raise ValueError("Arquivo de instrumentação já existe.")
    environment.worker_counts = Counter()
    environment.instrumentacao = {"conexoes": getattr(options, "conexoes", "reutilizar"),
                                  "registrar_worker_pid": getattr(options, "registrar_worker_pid", False)}
    latency_path = getattr(options, "latencias_saida", None)
    recorder = RegistroLatencias(latency_path, getattr(options, "limite_latencias", 100000)) if latency_path else None

    def save():
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(environment.instrumentacao, indent=2) + "\n", encoding="utf-8")

    def mark(field):
        environment.instrumentacao[field] = datetime.now(timezone.utc).isoformat()
        save()

    def started(**kw):
        environment.worker_counts.clear()
        mark("fase_inicio_utc")

    def ready(**kw):
        # Listener registrado em init, após o listener de reset do runner local.
        environment.worker_counts.clear()
        mark("usuarios_prontos_utc")
        if recorder:
            recorder.ativo = True

    def stopping(**kw):
        if recorder:
            recorder.ativo = False
        environment.instrumentacao["pids_janela"] = dict(environment.worker_counts)
        mark("encerramento_inicio_utc")

    def stopped(**kw):
        if recorder:
            recorder.fechar()
            environment.instrumentacao["latencias"] = recorder.metadados()
        environment.instrumentacao["pids_apos_encerramento"] = dict(environment.worker_counts)
        mark("fase_fim_utc")

    environment.events.test_start.add_listener(started)
    environment.events.spawning_complete.add_listener(ready)
    environment.events.test_stopping.add_listener(stopping)
    environment.events.test_stop.add_listener(stopped)
    if recorder:
        def request(name, response_time, exception=None, response=None, **kw):
            if name == "/primos":
                pid = response.headers.get("X-Worker-PID", "") if response is not None else ""
                recorder.registrar(time.time(), response_time, exception is not None, pid)
        environment.events.request.add_listener(request)


def registrar_pid(environment, response):
    if not getattr(environment.parsed_options, "registrar_worker_pid", False):
        return
    pid = response.headers.get("X-Worker-PID", "")
    key = str(int(pid)) if len(pid) <= 12 and pid.isascii() and pid.isdecimal() and int(pid) > 0 else "ausente_ou_invalido"
    environment.worker_counts[f"{key}/HTTP_{response.status_code}"] += 1


class UsuarioCPU(HttpUser):
    def wait_time(self):
        return self.environment.parsed_options.espera

    @task
    def primos(self):
        limite = self.environment.parsed_options.limite
        headers = {"Connection": "close"} if getattr(self.environment.parsed_options, "conexoes", "reutilizar") == "fechar" else {}
        with self.client.get(
            "/primos", params={"limite": limite}, name="/primos",
            timeout=30, catch_response=True, headers=headers,
        ) as response:
            registrar_pid(self.environment, response)
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                data = response.json()
            except ValueError:
                response.failure("Resposta não é JSON.")
                return
            if (not isinstance(data, dict)
                    or data.get("tipo") != "CPU-bound"
                    or data.get("limite") != limite
                    or type(data.get("quantidade_primos")) is not int
                    or not 0 <= data["quantidade_primos"] <= limite):
                response.failure("Formato ou parâmetros inesperados.")
