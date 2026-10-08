"""API para experimentos acadêmicos com ocupação temporária de RAM."""

import os
from mmap import ACCESS_COPY, PAGESIZE, mmap
from threading import BoundedSemaphore
from time import sleep
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


BYTES_POR_MB = 1024 * 1024
ORCAMENTO_MB = 256  # Teto de buffers por processo, pensado para a VM de 1 GB.
LIMITE_MINIMO_MB = int(os.getenv("MEMORY_LIMITE_MIN_MB", "1"))
LIMITE_MAXIMO_MB = int(os.getenv("MEMORY_LIMITE_MAX_MB", "64"))
MAX_SIMULTANEAS = int(os.getenv("MEMORY_MAX_SIMULTANEAS", "4"))
RETENCAO_SEGUNDOS = float(os.getenv("MEMORY_RETENCAO_SEGUNDOS", "0"))

if not 1 <= LIMITE_MINIMO_MB <= LIMITE_MAXIMO_MB:
    raise ValueError("Os limites de memória devem atender a 1 <= mínimo <= máximo.")
if MAX_SIMULTANEAS < 1 or LIMITE_MAXIMO_MB * MAX_SIMULTANEAS > ORCAMENTO_MB:
    raise ValueError("A concorrência deve ser positiva e máximo * simultâneas <= 256 MB.")
if not 0 <= RETENCAO_SEGUNDOS <= 5:
    raise ValueError("MEMORY_RETENCAO_SEGUNDOS deve estar entre 0 e 5 segundos.")

TAMANHO_PADRAO_MB = max(LIMITE_MINIMO_MB, min(50, LIMITE_MAXIMO_MB))
vagas = BoundedSemaphore(MAX_SIMULTANEAS)
app = FastAPI(title="Aplicação Memory-bound")


class RespostaMemoria(BaseModel):
    tipo: Literal["Memory-bound"]
    tamanho_mb: int
    verificacao: int


def alocar_memoria(tamanho_bytes: int) -> mmap:
    """Mapeamento anônimo com páginas privadas, sem arquivo de dados em disco."""
    return mmap(-1, tamanho_bytes, access=ACCESS_COPY)


def escrever_e_verificar(dados: mmap) -> int:
    """Escreve e lê um byte por página, sem cópias do buffer ou hash pesado."""
    for offset in range(0, len(dados), PAGESIZE):
        dados[offset] = 1
    # Inclui o fim da região, inclusive para tamanhos não múltiplos de página.
    dados[-1] = 1
    return sum(dados[offset] for offset in range(0, len(dados), PAGESIZE)) + dados[-1]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/memoria", response_model=RespostaMemoria)
def memoria(
    tamanho_mb: int = Query(
        default=TAMANHO_PADRAO_MB,
        ge=LIMITE_MINIMO_MB,
        le=LIMITE_MAXIMO_MB,
        description="Tamanho em MiB (1 MB nesta API = 1024 * 1024 bytes).",
    ),
) -> RespostaMemoria:
    # Não enfileira alocações nem permite que a concorrência esgote a RAM.
    if not vagas.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Limite de alocações simultâneas atingido.")

    try:
        with alocar_memoria(tamanho_mb * BYTES_POR_MB) as dados:
            verificacao = escrever_e_verificar(dados)
            # Retém a região somente depois da escrita/leitura, fora do event loop.
            if RETENCAO_SEGUNDOS > 0:
                sleep(RETENCAO_SEGUNDOS)
        return RespostaMemoria(
            tipo="Memory-bound", tamanho_mb=tamanho_mb, verificacao=verificacao
        )
    except (MemoryError, OSError):
        raise HTTPException(status_code=503, detail="Memória insuficiente para a alocação.") from None
    finally:
        vagas.release()
