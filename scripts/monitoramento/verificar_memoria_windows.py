"""Mede RAM e latência com uma e duas requisições, em três repetições.

Execute com o Python do .venv, a partir da raiz, com a porta 8002 livre.
Usa somente a biblioteca padrão e encerra apenas o servidor que iniciou.
"""

from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from threading import Barrier
import time
from urllib.request import urlopen


class ContadoresProcesso(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (nome, ctypes.c_size_t)
        for nome in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
        )
    ]


class MemoriaSistema(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + [
        (nome, ctypes.c_ulonglong)
        for nome in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual",
        )
    ]


def executar():
    if os.name != "nt":
        raise SystemExit("Este experimento usa APIs Windows; veja os comandos Linux no README.")
    raiz = Path(__file__).resolve().parents[2]
    inicio = time.perf_counter()
    instante = datetime.now(timezone(timedelta(hours=-3)))
    identificador = instante.strftime("%Y%m%d_%H%M%S_%f")
    saida = raiz / "experimentos/resultados" / f"memory_windows_{identificador}.json"
    pasta_temporaria = raiz / ".temp"
    pasta_temporaria.mkdir(exist_ok=True)
    log_servidor = pasta_temporaria / f"uvicorn_memory_{identificador}.stderr.log"
    resultados = {
        "inicio": instante.isoformat(), "timezone": "America/Sao_Paulo (UTC-03:00)",
        "python": sys.version, "fastapi": version("fastapi"), "uvicorn": version("uvicorn"),
        "workers": 1, "retencao_segundos": 5, "tamanho_por_requisicao_mib": 50,
        "repeticoes": 3, "intervalo_amostragem_s": 0.05,
        "temp": os.getenv("TEMP"), "tmp": os.getenv("TMP"),
        "temp_resolvido": tempfile.gettempdir(),
        "metodo": "GetProcessMemoryInfo: WorkingSetSize e PrivateUsage; GlobalMemoryStatusEx",
        "log_servidor": str(log_servidor), "ciclos": [], "erros": [],
    }
    # Recusa ocupar uma porta que já pertença a outro serviço.
    with socket.socket() as teste_porta:
        teste_porta.bind(("127.0.0.1", 8002))

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoriaSistema)]
    kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ContadoresProcesso), wintypes.DWORD
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    servidor = None
    handle = None
    stderr = None
    try:
        sistema = MemoriaSistema()
        sistema.dwLength = ctypes.sizeof(sistema)
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(sistema)):
            raise ctypes.WinError(ctypes.get_last_error())
        if sistema.ullAvailPhys < 512 * 2**20:
            raise RuntimeError("Experimento recusado: menos de 512 MiB de RAM física disponível.")
        ambiente = os.environ.copy()
        ambiente.update(MEMORY_LIMITE_MIN_MB="1", MEMORY_LIMITE_MAX_MB="64",
                        MEMORY_MAX_SIMULTANEAS="2", MEMORY_RETENCAO_SEGUNDOS="5")
        bootstrap = (
            'import os; print(os.getpid(), flush=True); import uvicorn; '
            'uvicorn.run("apps.memory_bound.main:app", host="127.0.0.1", '
            'port=8002, workers=1, log_level="error")'
        )
        stderr = log_servidor.open("x", encoding="utf-8")
        servidor = subprocess.Popen(
            [sys.executable, "-c", bootstrap], env=ambiente, cwd=raiz,
            stdout=subprocess.PIPE, stderr=stderr, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # O PID impresso é o interpretador real, inclusive com o launcher do venv.
        pid = int(servidor.stdout.readline())
        resultados["pid"] = pid
        handle = kernel.OpenProcess(0x0400 | 0x0010 | 0x0001, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        def observar(etapa):
            processo = ContadoresProcesso()
            processo.cb = ctypes.sizeof(processo)
            sistema = MemoriaSistema()
            sistema.dwLength = ctypes.sizeof(sistema)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(processo), processo.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.GlobalMemoryStatusEx(ctypes.byref(sistema)):
                raise ctypes.WinError(ctypes.get_last_error())
            return {
                "etapa": etapa, "tempo_desde_inicio_s": time.perf_counter() - inicio,
                "pid": pid, "processo_residente_bytes": processo.WorkingSetSize,
                "processo_privada_comprometida_bytes": processo.PrivateUsage,
                "sistema_total_fisica_bytes": sistema.ullTotalPhys,
                "sistema_disponivel_fisica_bytes": sistema.ullAvailPhys,
            }

        def pedir(caminho):
            with urlopen("http://127.0.0.1:8002" + caminho, timeout=10) as response:
                return json.load(response)

        prazo = time.monotonic() + 10
        while True:
            if servidor.poll() is not None:
                raise RuntimeError("O servidor terminou antes de ficar pronto.")
            try:
                pedir("/health")
                break
            except OSError:
                if time.monotonic() >= prazo:
                    raise
                time.sleep(0.1)

        # Aquece o processo; estes 5 segundos não entram nos ciclos medidos.
        pedir("/memoria?tamanho_mb=1")
        resultados["repouso_inicial"] = observar("repouso_inicial")
        for repeticao in range(1, 4):
            for concorrencia in (1, 2):
                antes = observar("antes")
                if antes["sistema_disponivel_fisica_bytes"] < 512 * 2**20:
                    raise RuntimeError("Carga interrompida: RAM física disponível abaixo de 512 MiB.")
                barreira = Barrier(concorrencia)

                def requisicao():
                    barreira.wait(timeout=5)
                    comeco = time.perf_counter() - inicio
                    try:
                        with urlopen("http://127.0.0.1:8002/memoria?tamanho_mb=50", timeout=15) as response:
                            status = response.status
                            corpo = json.load(response)
                        erro = None
                    except Exception as exc:
                        status = getattr(exc, "code", None)
                        corpo = None
                        erro = f"{type(exc).__name__}: {exc}"
                    fim = time.perf_counter() - inicio
                    return {"inicio_s": comeco, "fim_s": fim, "duracao_s": fim - comeco,
                            "status_http": status, "resposta": corpo, "erro": erro}

                amostras = []
                with ThreadPoolExecutor(max_workers=concorrencia) as executor:
                    pedidos = [executor.submit(requisicao) for _ in range(concorrencia)]
                    while not all(pedido.done() for pedido in pedidos):
                        amostras.append(observar("durante"))
                        time.sleep(0.05)
                    respostas = [pedido.result() for pedido in pedidos]
                apos_imediato = observar("apos_imediato")
                time.sleep(1)
                apos = observar("apos_1s")
                pico = max(amostras, key=lambda amostra: amostra["processo_residente_bytes"])
                ciclo = {
                    "repeticao": repeticao, "concorrencia": concorrencia, "antes": antes,
                    "pico": pico, "apos_imediato": apos_imediato, "apos_1s": apos,
                    "aumento_residente_pico_bytes": pico["processo_residente_bytes"] - antes["processo_residente_bytes"],
                    "variacao_residente_final_bytes": apos["processo_residente_bytes"] - antes["processo_residente_bytes"],
                    "sobreposicao_http_s": max(0, min(r["fim_s"] for r in respostas) - max(r["inicio_s"] for r in respostas)) if concorrencia == 2 else None,
                    "requisicoes": respostas, "amostras": amostras,
                }
                resultados["ciclos"].append(ciclo)
                for resposta in respostas:
                    if resposta["erro"] or resposta["status_http"] != 200:
                        resultados["erros"].append(resposta)
                print(json.dumps({
                    "repeticao": repeticao, "concorrencia": concorrencia,
                    "repouso_mib": round(antes["processo_residente_bytes"] / 2**20, 3),
                    "pico_mib": round(pico["processo_residente_bytes"] / 2**20, 3),
                    "apos_mib": round(apos["processo_residente_bytes"] / 2**20, 3),
                    "duracoes_s": [round(r["duracao_s"], 4) for r in respostas],
                    "sobreposicao_http_s": ciclo["sobreposicao_http_s"],
                }), flush=True)
        resultados["repouso_final"] = observar("repouso_final")
    except Exception as exc:
        resultados["erros"].append(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if handle:
            # Encerra o interpretador real; no Windows o launcher do venv pode
            # ser um processo distinto e seu término isolado deixaria um órfão.
            kernel.TerminateProcess(handle, 0)
            kernel.CloseHandle(handle)
        # O término é apenas do subprocesso criado para este experimento.
        if servidor is not None:
            if servidor.poll() is None:
                servidor.terminate()
            servidor.wait(timeout=5)
            servidor.stdout.close()
        if stderr is not None:
            stderr.close()
        resultados["duracao_total_s"] = time.perf_counter() - inicio
        resultados["fim"] = datetime.now(timezone(timedelta(hours=-3))).isoformat()
        with saida.open("x", encoding="utf-8") as arquivo:
            json.dump(resultados, arquivo, indent=2, ensure_ascii=False)
        print(f"Resultados registrados em: {saida}", flush=True)
    if resultados["erros"]:
        raise SystemExit("O experimento terminou com erros registrados no JSON.")


if __name__ == "__main__":
    executar()
