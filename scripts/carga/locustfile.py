"""Carga fechada e determinística: uma requisição por usuário a cada tarefa."""

import argparse
import math

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


class UsuarioCPU(HttpUser):
    def wait_time(self):
        return self.environment.parsed_options.espera

    @task
    def primos(self):
        limite = self.environment.parsed_options.limite
        with self.client.get(
            "/primos", params={"limite": limite}, name="/primos",
            timeout=30, catch_response=True,
        ) as response:
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
