"""API para experimentos acadêmicos com escrita e leitura de arquivos reais."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import BoundedSemaphore
from typing import BinaryIO, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel


BYTES_POR_MB = 1024 * 1024
TAMANHO_BLOCO = 64 * 1024
BLOCO = b"\xa5" * TAMANHO_BLOCO
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
DIRETORIO_TEMP = Path(os.getenv("IO_DIRETORIO_TEMP", ".temp/io_bound")).expanduser()
if not DIRETORIO_TEMP.is_absolute():
    DIRETORIO_TEMP = RAIZ_PROJETO / DIRETORIO_TEMP
DIRETORIO_TEMP = DIRETORIO_TEMP.resolve()
if DIRETORIO_TEMP == Path(DIRETORIO_TEMP.anchor):
    raise ValueError("IO_DIRETORIO_TEMP deve ser uma pasta dedicada, não a raiz da unidade.")

TAMANHO_MAXIMO_MB = int(os.getenv("IO_TAMANHO_MAX_MB", "32"))
OPERACOES_MAXIMAS = int(os.getenv("IO_OPERACOES_MAX", "5"))
MAX_SIMULTANEAS = int(os.getenv("IO_MAX_SIMULTANEAS", "2"))
VALOR_FSYNC = os.getenv("IO_FSYNC", "0")
if VALOR_FSYNC not in ("0", "1"):
    raise ValueError("IO_FSYNC deve ser 0 ou 1.")
FSYNC = VALOR_FSYNC == "1"

if min(TAMANHO_MAXIMO_MB, OPERACOES_MAXIMAS, MAX_SIMULTANEAS) < 1:
    raise ValueError("Os limites de I/O devem ser inteiros positivos.")
if TAMANHO_MAXIMO_MB * MAX_SIMULTANEAS > 128:
    raise ValueError("Tamanho máximo * simultâneas deve ser <= 128 MiB por processo.")
if TAMANHO_MAXIMO_MB * OPERACOES_MAXIMAS > 160:
    raise ValueError("Tamanho máximo * operações máximas deve ser <= 160 MiB escritos por pedido.")

TAMANHO_PADRAO_MB = min(10, TAMANHO_MAXIMO_MB)
vagas = BoundedSemaphore(MAX_SIMULTANEAS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cria somente a pasta configurada, na inicialização, sem varrer ou limpar dados.
    DIRETORIO_TEMP.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Aplicação I/O-bound", lifespan=lifespan)


class RespostaArquivo(BaseModel):
    tipo: Literal["I/O-bound"]
    tamanho_mb: int
    operacoes: int
    bytes_escritos: int
    bytes_lidos: int
    bytes_processados: int
    verificacao: Literal["ok"]


class ErroIntegridade(ValueError):
    pass


def processar_arquivo(arquivo: BinaryIO, tamanho_bytes: int) -> tuple[int, int]:
    """Escreve e verifica blocos sem carregar o arquivo inteiro na RAM."""
    escritos = 0
    while escritos < tamanho_bytes:
        bloco = BLOCO[:min(TAMANHO_BLOCO, tamanho_bytes - escritos)]
        if arquivo.write(bloco) != len(bloco):
            raise OSError("Escrita incompleta.")
        escritos += len(bloco)

    arquivo.flush()
    if FSYNC:
        os.fsync(arquivo.fileno())
    arquivo.seek(0)

    lidos = 0
    while lidos < tamanho_bytes:
        quantidade = min(TAMANHO_BLOCO, tamanho_bytes - lidos)
        bloco = arquivo.read(quantidade)
        if bloco != BLOCO[:quantidade]:
            raise ErroIntegridade("Conteúdo incorreto ou arquivo truncado.")
        lidos += len(bloco)
    if arquivo.read(1):
        raise ErroIntegridade("Arquivo contém bytes extras.")
    return escritos, lidos


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/arquivo", response_model=RespostaArquivo)
def arquivo(
    tamanho_mb: int = Query(default=TAMANHO_PADRAO_MB, ge=1, le=TAMANHO_MAXIMO_MB),
    operacoes: int = Query(default=1, ge=1, le=OPERACOES_MAXIMAS),
) -> RespostaArquivo:
    if not vagas.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Limite de operações simultâneas atingido.")
    escritos = lidos = 0
    try:
        for _ in range(operacoes):
            # Um arquivo exclusivo por operação; o contexto remove somente este arquivo.
            # Escrita e leitura usam o mesmo handle, compatível com Windows e Linux.
            with NamedTemporaryFile(mode="w+b", dir=DIRETORIO_TEMP,
                                    prefix="io_bound_", suffix=".tmp") as temporario:
                bytes_escritos, bytes_lidos = processar_arquivo(
                    temporario, tamanho_mb * BYTES_POR_MB
                )
                escritos += bytes_escritos
                lidos += bytes_lidos
        return RespostaArquivo(
            tipo="I/O-bound", tamanho_mb=tamanho_mb, operacoes=operacoes,
            bytes_escritos=escritos, bytes_lidos=lidos,
            bytes_processados=escritos + lidos, verificacao="ok",
        )
    except ErroIntegridade:
        raise HTTPException(status_code=500, detail="Falha na verificação do arquivo.") from None
    except OSError:
        raise HTTPException(status_code=507, detail="Falha de I/O ao processar o arquivo temporário.") from None
    finally:
        vagas.release()
