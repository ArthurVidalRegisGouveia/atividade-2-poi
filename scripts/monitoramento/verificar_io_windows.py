"""Validação local T1–T4; não altera aplicações nem apaga arquivos preexistentes.

Na raiz, execute com o Python do .venv e a porta 8003 livre.
Os contadores do volume D: podem exigir execução fora do sandbox.
"""

import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import socket
from statistics import mean
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen


CAMPOS_IO = (
    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
)
CAMPOS_DISCO = (
    "DiskReadBytesPersec", "DiskWriteBytesPersec", "DiskReadsPersec", "DiskWritesPersec",
)


class ContadoresIO(ctypes.Structure):
    _fields_ = [(campo, ctypes.c_ulonglong) for campo in CAMPOS_IO]


def coletar_volume():
    # Dados RAW: as propriedades de taxa contêm contadores acumulados.
    # Os deltas são bytes/operações na janela, não valores já expressos por segundo.
    comando = (
        "$ErrorActionPreference='Stop'; "
        "Get-CimInstance Win32_PerfRawData_PerfDisk_LogicalDisk | "
        "Where-Object Name -eq 'D:' | Select-Object Name, "
        "DiskReadBytesPersec, DiskWriteBytesPersec, DiskReadsPersec, DiskWritesPersec, "
        "Timestamp_PerfTime, Frequency_PerfTime | ConvertTo-Json -Compress"
    )
    coleta = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", comando],
        capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if coleta.returncode != 0:
        return {"erro": coleta.stderr.strip() or "Consulta CIM falhou."}
    if not coleta.stdout.strip():
        return {"erro": "O provedor não retornou o volume D:."}
    return json.loads(coleta.stdout)


def executar():
    if os.name != "nt":
        raise SystemExit("Este experimento usa contadores nativos do Windows.")
    raiz = Path(__file__).resolve().parents[2]
    temp = raiz / ".temp"
    temp.mkdir(exist_ok=True)
    # Apenas o ambiente desta execução e dos filhos; nada é persistido no Windows.
    os.environ["TEMP"] = os.environ["TMP"] = str(temp)
    instante = datetime.now(timezone(timedelta(hours=-3)))
    identificador = instante.strftime("%Y%m%d_%H%M%S_%f")
    diretorio = temp / f"io_validation_{identificador}"
    diretorio.mkdir()  # Nome exclusivo; não reutiliza nem limpa diretórios existentes.
    saida = raiz / "experimentos/resultados" / f"io_windows_{identificador}.json"
    with socket.socket() as porta:
        porta.bind(("127.0.0.1", 8003))
    caminhos_apps = [raiz / f"apps/{nome}/main.py" for nome in ("cpu_bound", "memory_bound", "io_bound")]

    def hashes():
        return {str(path.relative_to(raiz)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in caminhos_apps}

    dados = {
        "inicio": instante.isoformat(), "timezone": "America/Sao_Paulo (UTC-03:00)",
        "python": sys.version, "fastapi": version("fastapi"), "uvicorn": version("uvicorn"),
        "workers": 1, "diretorio_io": str(diretorio), "temp": str(temp),
        "limites": {"IO_TAMANHO_MAX_MB": 32, "IO_OPERACOES_MAX": 5, "IO_MAX_SIMULTANEAS": 1},
        "espaco_antes": shutil.disk_usage(diretorio)._asdict(),
        "hashes_antes": hashes(), "resultados": [], "servidores": [], "erros": [],
        "metodo_processo": "GetProcessIoCounters; deltas de I/O do processo inteiro, não I/O físico",
        "metodo_volume": "CIM Win32_PerfRawData_PerfDisk_LogicalDisk, instância D:; deltas de contadores RAW",
        "espera_apos_http_s": 1,
        "limite_atribuicao": "Contadores do volume incluem outros processos e caches do dispositivo; não identificam gravações na mídia exclusivamente desta API.",
    }
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(ContadoresIO)]
    kernel.GetProcessIoCounters.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def processo_io(handle):
        counters = ContadoresIO()
        if not kernel.GetProcessIoCounters(handle, ctypes.byref(counters)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {campo: getattr(counters, campo) for campo in CAMPOS_IO}

    def pedido(caminho):
        inicio = time.perf_counter()
        try:
            with urlopen("http://127.0.0.1:8003" + caminho, timeout=30) as response:
                corpo = json.load(response)
                status = response.status
            erro = None
        except HTTPError as exc:
            corpo = exc.read().decode("utf-8", errors="replace")
            status, erro = exc.code, str(exc)
        except OSError as exc:
            corpo, status, erro = None, None, str(exc)
        return {"duracao_http_s": time.perf_counter() - inicio,
                "status_http": status, "resposta": corpo, "erro": erro}

    cenarios = [("T1", 1, 1, 0), ("T2", 10, 1, 0), ("T3", 10, 1, 1), ("T4", 10, 5, 1)]
    try:
        for fsync in (0, 1):
            ambiente = os.environ.copy()
            ambiente.update(IO_DIRETORIO_TEMP=str(diretorio), IO_TAMANHO_MAX_MB="32",
                            IO_OPERACOES_MAX="5", IO_MAX_SIMULTANEAS="1", IO_FSYNC=str(fsync))
            log = temp / f"uvicorn_io_{identificador}_fsync{fsync}.stderr.log"
            bootstrap = (
                'import os; print(os.getpid(), flush=True); import uvicorn; '
                'uvicorn.run("apps.io_bound.main:app", host="127.0.0.1", '
                'port=8003, workers=1, log_level="error")'
            )
            handle = None
            servidor = None
            with log.open("x", encoding="utf-8") as stderr:
                try:
                    servidor = subprocess.Popen(
                        [sys.executable, "-c", bootstrap], cwd=raiz, env=ambiente,
                        stdout=subprocess.PIPE, stderr=stderr, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    pid = int(servidor.stdout.readline())
                    handle = kernel.OpenProcess(0x0400 | 0x0001, False, pid)
                    if not handle:
                        raise ctypes.WinError(ctypes.get_last_error())
                    prazo = time.monotonic() + 15
                    while pedido("/health")["status_http"] != 200:
                        if servidor.poll() is not None or time.monotonic() > prazo:
                            raise RuntimeError("O Uvicorn não ficou pronto; consulte o log.")
                        time.sleep(0.1)
                    aquecimento = pedido("/arquivo?tamanho_mb=1&operacoes=1")
                    dados["servidores"].append({"pid": pid, "fsync": fsync,
                                               "log": str(log), "aquecimento": aquecimento})
                    if aquecimento["status_http"] != 200 or list(diretorio.iterdir()):
                        raise RuntimeError("O aquecimento falhou ou deixou arquivos temporários.")
                    for nome, tamanho, operacoes, modo in cenarios:
                        if modo != fsync:
                            continue
                        for repeticao in range(1, 4):
                            espaco = shutil.disk_usage(diretorio)
                            if espaco.free < 1024 * 1024 * 1024:
                                raise RuntimeError("Carga recusada: menos de 1 GiB livre no diretório de I/O.")
                            antes_arquivos = [path.name for path in diretorio.iterdir()]
                            if antes_arquivos:
                                raise RuntimeError("Pasta não está vazia; nenhum resíduo será apagado.")
                            volume_antes = coletar_volume()
                            processo_antes = processo_io(handle)
                            resultado = pedido(f"/arquivo?tamanho_mb={tamanho}&operacoes={operacoes}")
                            processo_depois = processo_io(handle)
                            depois_arquivos = [path.name for path in diretorio.iterdir()]
                            # Janela de observação externa; não entra no tempo HTTP nem na API.
                            time.sleep(1)
                            volume_depois = coletar_volume()
                            volume_delta = None
                            if "erro" not in volume_antes and "erro" not in volume_depois:
                                volume_delta = {campo: volume_depois[campo] - volume_antes[campo]
                                                for campo in CAMPOS_DISCO}
                                volume_delta["janela_contador_s"] = (
                                    volume_depois["Timestamp_PerfTime"] - volume_antes["Timestamp_PerfTime"]
                                ) / volume_depois["Frequency_PerfTime"]
                                if min(volume_delta.values()) < 0 or volume_delta["janela_contador_s"] <= 0:
                                    volume_delta = None
                            esperado = tamanho * 2**20 * operacoes
                            valido = resultado["status_http"] == 200 and isinstance(resultado["resposta"], dict)
                            if valido:
                                corpo = resultado["resposta"]
                                valido = (corpo.get("bytes_escritos") == esperado
                                          and corpo.get("bytes_lidos") == esperado
                                          and corpo.get("bytes_processados") == 2 * esperado
                                          and corpo.get("verificacao") == "ok")
                            registro = {
                                "cenario": nome, "repeticao": repeticao, "tamanho_mb": tamanho,
                                "operacoes": operacoes, "fsync": fsync, "pid": pid, **resultado,
                                "bytes_resposta_corretos": valido, "arquivos_antes": antes_arquivos,
                                "arquivos_apos": depois_arquivos, "espaco_livre_antes_bytes": espaco.free,
                                "processo_antes": processo_antes, "processo_depois": processo_depois,
                                "processo_delta": {campo: processo_depois[campo] - processo_antes[campo]
                                                   for campo in CAMPOS_IO},
                                "volume_antes": volume_antes, "volume_depois": volume_depois,
                                "volume_delta": volume_delta,
                            }
                            dados["resultados"].append(registro)
                            if not valido or depois_arquivos:
                                dados["erros"].append({"cenario": nome, "repeticao": repeticao,
                                                       "erro": "Resposta inválida ou limpeza incompleta."})
                            print(json.dumps({"cenario": nome, "repeticao": repeticao,
                                              "tempo_ms": resultado["duracao_http_s"] * 1000,
                                              "status": resultado["status_http"],
                                              "volume_delta": volume_delta,
                                              "arquivos_apos": depois_arquivos}), flush=True)
                finally:
                    if handle:
                        kernel.TerminateProcess(handle, 0)
                        kernel.CloseHandle(handle)
                    if servidor is not None:
                        if servidor.poll() is None:
                            servidor.terminate()
                        servidor.wait(timeout=5)
                        servidor.stdout.close()
    except Exception as exc:
        dados["erros"].append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        dados["hashes_depois"] = hashes()
        dados["espaco_depois"] = shutil.disk_usage(diretorio)._asdict()
        dados["arquivos_finais"] = [path.name for path in diretorio.iterdir()]
        dados["medias_http_s"] = {
            nome: mean(r["duracao_http_s"] for r in dados["resultados"] if r["cenario"] == nome)
            for nome in {r["cenario"] for r in dados["resultados"]}
        }
        dados["fim"] = datetime.now(timezone(timedelta(hours=-3))).isoformat()
        with saida.open("x", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, indent=2, ensure_ascii=False)
        print(f"Resultado: {saida}", flush=True)
    if dados["erros"]:
        raise SystemExit("O experimento registrou erros; consulte o JSON.")


if __name__ == "__main__":
    executar()
