"""Sondagens explícitas de /health; não são parte da carga Locust."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def utc():
    return datetime.now(timezone.utc)


def calcular(t1, t2, t3, t4, rtt):
    if any(t.tzinfo is None for t in (t1, t2, t3, t4)):
        raise ValueError("Todos os horários precisam de timezone.")
    wall = (t4 - t1).total_seconds()
    server = (t3 - t2).total_seconds()
    lower, upper = (t3 - t4).total_seconds(), (t2 - t1).total_seconds()
    if rtt < 0 or server < 0 or lower > upper or abs(wall - rtt) > 0.05:
        raise ValueError("Horários inconsistentes ou relógio ajustado durante sondagem.")
    return {"offset_servidor_menos_cliente_min_s": lower,
            "offset_servidor_menos_cliente_max_s": upper,
            "offset_estimado_s": (lower + upper) / 2,
            "incerteza_meia_faixa_s": (upper - lower) / 2,
            "rtt_monotonico_s": rtt, "tempo_servidor_s": server,
            "transito_e_overhead_s": wall - server}


def sondar(url):
    t1, start = utc(), time.monotonic()
    with urlopen(Request(url.rstrip("/") + "/health", headers={"Connection": "close"}), timeout=5) as response:
        response.read()
        headers = response.headers
    end, t4 = time.monotonic(), utc()
    t2 = datetime.fromisoformat(headers["X-Server-Received-UTC"])
    t3 = datetime.fromisoformat(headers["X-Server-Sent-UTC"])
    result = calcular(t1, t2, t3, t4, end - start)
    result.update(t1_utc=t1.isoformat(), t2_utc=t2.isoformat(), t3_utc=t3.isoformat(), t4_utc=t4.isoformat())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--amostras", type=int, choices=range(1, 21), default=5)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args(argv)
    target = urlsplit(args.url)
    if target.scheme not in ("http", "https") or not target.hostname or target.username or target.password or target.query or target.fragment or target.path not in ("", "/"):
        parser.error("URL precisa ser origem HTTP(S) sem credenciais.")
    if args.saida.exists():
        parser.error("Saída já existe; escolha arquivo novo.")
    records = []
    for _ in range(args.amostras):
        try:
            records.append(sondar(args.url))
        except (OSError, ValueError, TypeError, KeyError) as error:
            records.append({"erro": type(error).__name__, "detalhe": str(error)})
    valid = [record for record in records if "erro" not in record]
    best = min(valid, key=lambda record: record["incerteza_meia_faixa_s"]) if valid else None
    data = {"url": args.url, "coletado_utc": utc().isoformat(), "amostras": records,
            "menor_incerteza": best, "modelo": "offset servidor-cliente; estimativa assume trânsito simétrico",
            "sincronizacao_confirmada_automaticamente": False}
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with args.saida.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2)
        output.write("\n")
    print(f"Sondagens: {len(valid)}/{len(records)} válidas; arquivo {args.saida}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
