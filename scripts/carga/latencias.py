"""Registro local limitado e bufferizado; sem manter latências na RAM."""

import csv
from datetime import datetime, timezone
import math
from pathlib import Path


class RegistroLatencias:
    def __init__(self, path, limite=100000):
        if type(limite) is not int or not 1 <= limite <= 1000000:
            raise ValueError("Limite de registros deve estar entre 1 e 1000000.")
        self.file = Path(path).open("x", encoding="utf-8", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(["concluida_utc", "latencia_ms", "falha", "worker_pid"])
        self.limite = limite
        self.registros = self.descartados = self.invalidos = 0
        self.erros_escrita = 0
        self.ativo = False

    def registrar(self, timestamp, latencia, falha, pid=""):
        if not self.ativo or self.file.closed:
            return
        if self.registros >= self.limite:
            self.descartados += 1
            return
        try:
            latencia = float(latencia)
            if not math.isfinite(latencia) or latencia < 0:
                raise ValueError("Latência inválida")
        except (TypeError, ValueError):
            self.invalidos += 1
            latencia = ""
        try:
            self.writer.writerow([datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                                  latencia, int(bool(falha)), pid])
        except OSError:
            self.erros_escrita += 1
            self.ativo = False
            return
        self.registros += 1

    def fechar(self):
        self.ativo = False
        try:
            self.file.close()
        except OSError:
            self.erros_escrita += 1

    def metadados(self):
        return dict(registros=self.registros, descartados=self.descartados,
                    invalidos=self.invalidos, limite=self.limite,
                    erros_escrita=self.erros_escrita,
                    completo=self.file.closed and not self.descartados and not self.invalidos and not self.erros_escrita,
                    unidade="ms", timestamp="UTC de conclusão no evento request do Locust",
                    percentil="empírico: posto ceil(0.95*n), sem arredondamento Locust")
