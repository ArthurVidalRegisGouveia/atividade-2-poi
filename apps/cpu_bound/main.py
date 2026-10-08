"""API para experimentos acadêmicos com carga de CPU."""

import os
from datetime import datetime, timezone
from math import isqrt
from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel


LIMITE_MAXIMO = int(os.getenv("CPU_LIMITE_MAX", "1000000"))
if LIMITE_MAXIMO < 1:
    raise ValueError("CPU_LIMITE_MAX deve ser um inteiro positivo.")

# Mantém a requisição sem parâmetro válida mesmo com um teto menor.
LIMITE_PADRAO = min(100000, LIMITE_MAXIMO)

app = FastAPI(title="Aplicação CPU-bound")


class DiagnosticoExperimental:
    """Cabeçalhos opcionais, sem alterar corpo ou processamento matemático."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        received = datetime.now(timezone.utc).isoformat().encode("ascii")

        async def diagnostic_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-worker-pid", str(os.getpid()).encode("ascii")),
                    (b"x-server-received-utc", received),
                    (b"x-server-sent-utc", datetime.now(timezone.utc).isoformat().encode("ascii")),
                ]
            await send(message)

        await self.app(scope, receive, diagnostic_send)


if os.getenv("CPU_DIAGNOSTICO", "0") == "1":
    app.add_middleware(DiagnosticoExperimental)


class RespostaPrimos(BaseModel):
    tipo: Literal["CPU-bound"]
    limite: int
    quantidade_primos: int


def contar_primos(limite: int) -> int:
    """Conta primos até o limite (inclusive), sem armazenar uma lista deles."""
    quantidade = 1 if limite >= 2 else 0
    for candidato in range(3, limite + 1, 2):
        for divisor in range(3, isqrt(candidato) + 1, 2):
            if candidato % divisor == 0:
                break
        else:
            quantidade += 1
    return quantidade


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/primos", response_model=RespostaPrimos)
def primos(
    limite: int = Query(
        default=LIMITE_PADRAO,
        ge=1,
        le=LIMITE_MAXIMO,
        description="Limite inclusivo para a contagem de números primos.",
    ),
) -> RespostaPrimos:
    return RespostaPrimos(
        tipo="CPU-bound",
        limite=limite,
        quantidade_primos=contar_primos(limite),
    )
