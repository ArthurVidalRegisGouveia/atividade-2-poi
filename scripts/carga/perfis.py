"""Perfis das APIs existentes; configuração do servidor é declarada pelo operador."""

import math

PERFIS = {
    "cpu": {"endpoint": "/primos", "tipo": "CPU-bound", "porta": 8001},
    "memoria": {"endpoint": "/memoria", "tipo": "Memory-bound", "porta": 8002},
    "io": {"endpoint": "/arquivo", "tipo": "I/O-bound", "porta": 8003},
}
PADROES_SERVIDOR = {
    "cpu": {"CPU_LIMITE_MAX": 1000000, "CPU_DIAGNOSTICO": 0},
    "memoria": {"MEMORY_LIMITE_MIN_MB": 1, "MEMORY_LIMITE_MAX_MB": 64,
                "MEMORY_MAX_SIMULTANEAS": 4, "MEMORY_RETENCAO_SEGUNDOS": 0},
    "io": {"IO_TAMANHO_MAX_MB": 32, "IO_OPERACOES_MAX": 5, "IO_MAX_SIMULTANEAS": 2,
           "IO_FSYNC": 0, "IO_DIRETORIO_TEMP": ".temp/io_bound"},
}


def configurar_servidor(aplicacao, supplied=None, retencao=None, fsync=None):
    config = PADROES_SERVIDOR[aplicacao].copy()
    supplied = {} if supplied is None else supplied
    if not isinstance(supplied, dict) or set(supplied) - set(config):
        raise ValueError("Configuração do servidor deve conter somente variáveis do perfil escolhido.")
    config.update(supplied)
    for key, value in config.items():
        if key == "IO_DIRETORIO_TEMP":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Diretório I/O deve ser uma string não vazia.")
        elif key == "MEMORY_RETENCAO_SEGUNDOS":
            config[key] = float(value)
        else:
            if isinstance(value, bool) or str(value) != str(int(value)):
                raise ValueError(f"{key}: inteiro esperado.")
            config[key] = int(value)
    if retencao is not None:
        if aplicacao != "memoria":
            raise ValueError("Retenção só existe na aplicação memoria.")
        if "MEMORY_RETENCAO_SEGUNDOS" in supplied and config["MEMORY_RETENCAO_SEGUNDOS"] != retencao:
            raise ValueError("Retenção diverge do JSON declarado.")
        config["MEMORY_RETENCAO_SEGUNDOS"] = retencao
    if fsync is not None:
        if aplicacao != "io":
            raise ValueError("fsync só existe na aplicação io.")
        if "IO_FSYNC" in supplied and config["IO_FSYNC"] != fsync:
            raise ValueError("fsync diverge do JSON declarado.")
        config["IO_FSYNC"] = fsync
    if aplicacao == "cpu" and config["CPU_LIMITE_MAX"] < 1:
        raise ValueError("CPU_LIMITE_MAX deve ser positivo.")
    if aplicacao == "cpu" and config["CPU_DIAGNOSTICO"] not in (0, 1):
        raise ValueError("Declaração CPU_DIAGNOSTICO deve ser 0 ou 1.")
    if aplicacao == "memoria":
        low, high, simultaneous, hold = (config[key] for key in PADROES_SERVIDOR[aplicacao])
        if not 1 <= low <= high or simultaneous < 1 or high * simultaneous > 256:
            raise ValueError("Memória: mínimo/máximo/concorrência incompatíveis com orçamento de 256 MiB por worker.")
        if not math.isfinite(hold) or not 0 <= hold <= 5:
            raise ValueError("Retenção deve estar entre 0 e 5 s.")
    if aplicacao == "io":
        high, operations, simultaneous = (config[key] for key in ("IO_TAMANHO_MAX_MB", "IO_OPERACOES_MAX", "IO_MAX_SIMULTANEAS"))
        if min(high, operations, simultaneous) < 1 or high * simultaneous > 128 or high * operations > 160:
            raise ValueError("I/O: limites excedem os orçamentos da API.")
        if config["IO_FSYNC"] not in (0, 1):
            raise ValueError("IO_FSYNC deve ser 0 ou 1.")
    return config


def pedido(options):
    app = getattr(options, "aplicacao", "cpu")
    if app == "cpu":
        params = {"limite": options.limite}
    else:
        size = getattr(options, "tamanho_mb", None)
        params = {"tamanho_mb": size if size is not None else (50 if app == "memoria" else 10)}
        if app == "io":
            params["operacoes"] = getattr(options, "operacoes", None) or 1
    return PERFIS[app]["endpoint"], params


def resposta_valida(aplicacao, params, data):
    if not isinstance(data, dict) or data.get("tipo") != PERFIS[aplicacao]["tipo"]:
        return False
    if any(type(data.get(key)) is not int or data[key] != value for key, value in params.items()):
        return False
    if aplicacao == "cpu":
        return type(data.get("quantidade_primos")) is int and 0 <= data["quantidade_primos"] <= params["limite"]
    if aplicacao == "memoria":
        # Tamanho de página depende do servidor; não presume PAGESIZE do Windows.
        return type(data.get("verificacao")) is int and data["verificacao"] > 0
    count = params["tamanho_mb"] * 1048576 * params["operacoes"]
    return (data.get("verificacao") == "ok"
            and all(type(data.get(key)) is int and data[key] == expected
                    for key, expected in [("bytes_escritos", count), ("bytes_lidos", count), ("bytes_processados", 2 * count)]))
