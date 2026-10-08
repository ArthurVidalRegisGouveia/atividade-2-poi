"""Amostragem da VM e da árvore do PID principal, sem controle do servidor."""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import psutil

VERSION = "1.1.0"
SCENARIOS = {
    "C1": {"vcpus": 1, "ram_gib": 1, "workers": 1},
    "C2": {"vcpus": 1, "ram_gib": 2, "workers": 1},
    "C3": {"vcpus": 2, "ram_gib": 1, "workers": 2},
    "C4": {"vcpus": 2, "ram_gib": 2, "workers": 2},
}
SYSTEM_FIELDS = [
    "amostra", "utc", "tempo_relativo_s", "intervalo_real_s", "cpus_logicas",
    "cpu_sistema_capacidade_pct", "ram_total_bytes", "ram_disponivel_bytes",
    "ram_usada_psutil_bytes", "ram_nao_disponivel_bytes", "ram_percent_psutil",
    "processos_enumerados", "cpu_processos_completa", "cpu_soma_uma_cpu_pct",
    "cpu_soma_capacidade_vm_pct", "rss_soma_bytes", "uss_soma_bytes", "pss_soma_bytes",
    "processos_adicionados", "processos_removidos",
]
PROCESS_FIELDS = [
    "amostra", "utc", "tempo_relativo_s", "pid", "criado_epoch_s", "papel",
    "cpu_intervalo_real_s", "cpu_uma_cpu_pct", "cpu_capacidade_vm_pct", "rss_bytes", "vms_bytes",
    "uss_bytes", "pss_bytes", "erro",
]


def positivo(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Informe um inteiro positivo.")
    return number


def segundos(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Informe segundos finitos e positivos.")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pid", type=positivo, required=True)
    result.add_argument("--cenario", choices=SCENARIOS, required=True)
    result.add_argument("--usuarios", type=positivo, required=True)
    result.add_argument("--repeticao", type=positivo, default=1)
    result.add_argument("--intervalo", type=segundos, default=1.0)
    result.add_argument("--duracao", type=segundos, help="Sem valor: até Ctrl+C.")
    result.add_argument("--resultados", type=Path, default=Path("experimentos/resultados/carga"))
    result.add_argument("--memoria-detalhada", action="store_true", help="Coletar USS/PSS, com maior custo.")
    result.add_argument("--condicoes", default="", help="Notas experimentais sem segredos ou dados pessoais.")
    result.add_argument("--diagnostico-cpu", action="store_true", help="JSONL com /proc/stat e contadores dos processos.")
    return result


def utc():
    return datetime.now(timezone.utc).isoformat()


class PrincipalEncerrado(Exception):
    pass


def contadores_sistema():
    before = time.monotonic()
    try:
        lines = [line for line in Path("/proc/stat").read_text(encoding="ascii").splitlines()
                 if line.startswith("cpu")]
        ticks = os.sysconf("SC_CLK_TCK")
        result = {"proc_stat_cpu_linhas": lines, "clk_tck": ticks}
    except (OSError, AttributeError, ValueError) as error:
        result = {"erro": type(error).__name__}
    return dict(result, utc=utc(), monotonic_before_s=before, monotonic_after_s=time.monotonic())


class Coletor:
    def __init__(self, pid, detailed=False, diagnostic=False):
        self.root = psutil.Process(pid)
        self.identity = (pid, self.root.create_time())
        self.detailed = detailed
        self.diagnostic = diagnostic
        self.raw_initial = contadores_sistema() if diagnostic else None
        self.last_raw = None
        self.previous_cpu = {}
        self.previous_ids = set()
        self.cpus = psutil.cpu_count(logical=True)
        if not self.cpus:
            raise RuntimeError("Não foi possível identificar CPUs lógicas.")
        # A primeira chamada não bloqueante não constitui uma medição válida.
        psutil.cpu_percent(interval=None)

    def sample(self, index, elapsed, delta):
        try:
            if not self.root.is_running() or self.root.status() == psutil.STATUS_ZOMBIE:
                raise PrincipalEncerrado("PID principal encerrado ou reutilizado.")
            processes = [self.root] + self.root.children(recursive=True)
        except psutil.NoSuchProcess as error:
            raise PrincipalEncerrado("PID principal encerrado.") from error
        stamp = utc()
        rows, current_cpu, identities = [], {}, set()
        raw_processes = []
        for process in {p.pid: p for p in processes}.values():
            row = dict.fromkeys(PROCESS_FIELDS)
            row.update(amostra=index, utc=stamp, tempo_relativo_s=elapsed,
                       pid=process.pid, papel="principal" if process.pid == self.root.pid else "descendente")
            try:
                if not process.is_running():
                    raise psutil.NoSuchProcess(process.pid)
                created = process.create_time()
                identity = (process.pid, created)
                identities.add(identity)
                row["criado_epoch_s"] = created
                cpu = process.cpu_times()
                observed = time.monotonic()
                total = cpu.user + cpu.system  # Não inclui CPU dos filhos.
                previous = self.previous_cpu.get(identity)
                if self.diagnostic:
                    raw = {"pid": process.pid, "criado_epoch_s": created,
                           "cpu_times_s": cpu._asdict(), "monotonic_s": observed,
                           "anterior": previous}
                    try:
                        raw.update(ppid=process.ppid(), cmdline=process.cmdline())
                    except psutil.Error as error:
                        raw["erro_identificacao"] = type(error).__name__
                    raw_processes.append(raw)
                current_cpu[identity] = (total, observed)
                if previous and observed > previous[1]:
                    row["cpu_intervalo_real_s"] = observed - previous[1]
                    row["cpu_uma_cpu_pct"] = max(0, total - previous[0]) / (observed - previous[1]) * 100
                    row["cpu_capacidade_vm_pct"] = row["cpu_uma_cpu_pct"] / self.cpus
                memory = process.memory_info()
                row.update(rss_bytes=memory.rss, vms_bytes=memory.vms)
                if self.detailed:
                    try:
                        full = process.memory_full_info()
                        row.update(uss_bytes=getattr(full, "uss", None), pss_bytes=getattr(full, "pss", None))
                    except (psutil.Error, NotImplementedError) as error:
                        row["erro"] = f"memoria_detalhada:{type(error).__name__}"
            except psutil.Error as error:
                row["erro"] = type(error).__name__
            rows.append(row)
        memory = psutil.virtual_memory()
        system = dict(amostra=index, utc=stamp, tempo_relativo_s=elapsed,
                      intervalo_real_s=delta, cpus_logicas=self.cpus,
                      cpu_sistema_capacidade_pct=psutil.cpu_percent(interval=None),
                      ram_total_bytes=memory.total, ram_disponivel_bytes=memory.available,
                      ram_usada_psutil_bytes=memory.used,
                      ram_nao_disponivel_bytes=memory.total - memory.available,
                      ram_percent_psutil=memory.percent, processos_enumerados=len(rows))
        for field, target in [("cpu_uma_cpu_pct", "cpu_soma_uma_cpu_pct"),
                              ("cpu_capacidade_vm_pct", "cpu_soma_capacidade_vm_pct"),
                              ("rss_bytes", "rss_soma_bytes"), ("uss_bytes", "uss_soma_bytes"),
                              ("pss_bytes", "pss_soma_bytes")]:
            values = [r[field] for r in rows]
            system[target] = sum(values) if values and all(v is not None for v in values) else None
        system["cpu_processos_completa"] = system["cpu_soma_uma_cpu_pct"] is not None
        system["processos_adicionados"] = json.dumps(sorted(identities - self.previous_ids))
        system["processos_removidos"] = json.dumps(sorted(self.previous_ids - identities))
        self.previous_cpu, self.previous_ids = current_cpu, identities
        if self.diagnostic:
            self.last_raw = {"amostra": index, "utc_amostra": stamp,
                             "sistema": contadores_sistema(), "processos": raw_processes}
        return system, rows


def executar(options, collector):
    base = (options.resultados / options.cenario / f"usuarios_{options.usuarios:02d}"
            / f"repeticao_{options.repeticao:02d}" / "monitoramento_linux")
    # Pode coexistir com CSV do Locust, mas nunca sobrescreve uma coleta existente.
    base.mkdir(parents=True, exist_ok=False)
    metadata = {
        "versao_script": VERSION, "psutil": psutil.__version__, "python": platform.python_version(),
        "sistema": platform.system(), "kernel": platform.release(), "inicio_utc": utc(),
        "pid_principal": options.pid, "criado_epoch_s": collector.identity[1],
        "cenario": options.cenario, "usuarios": options.usuarios, "repeticao": options.repeticao,
        "provisionamento_planejado": SCENARIOS[options.cenario],
        "cpus_logicas_observadas": collector.cpus, "ram_total_observada_bytes": psutil.virtual_memory().total,
        "intervalo_s": options.intervalo, "duracao_s": options.duracao,
        "memoria_detalhada": options.memoria_detalhada, "condicoes": options.condicoes,
        "uid_efetivo": os.geteuid() if hasattr(os, "geteuid") else None,
        "cpu_processos_base": "100 * delta(user+system) / delta(monotonic), 100% = uma CPU lógica",
        "cpu_processos_normalizada": "cpu_processos_base / cpus_logicas_observadas",
        "cpu_sistema_base": "psutil.cpu_percent(interval=None), 100% = capacidade total",
        "memoria": "bytes; RSS somado pode contar páginas compartilhadas várias vezes",
        "estado": "executando", "amostras": 0,
        "diagnostico_cpu": options.diagnostico_cpu,
        "contadores_brutos": "cpu_bruto.jsonl; ticks /proc/stat e segundos CPU por processo; leituras sequenciais",
    }
    metadata_path = base / "metadados.json"

    def salvar():
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    salvar()
    started = time.monotonic()
    last, deadline = started, started + options.intervalo
    raw_file = None
    print(f"Coleta em {base}; Ctrl+C encerra sem finalizar o servidor.")
    try:
        with (base / "sistema.csv").open("x", encoding="utf-8", newline="") as system_file, \
                (base / "processos.csv").open("x", encoding="utf-8", newline="") as process_file:
            system_writer = csv.DictWriter(system_file, fieldnames=SYSTEM_FIELDS)
            process_writer = csv.DictWriter(process_file, fieldnames=PROCESS_FIELDS)
            system_writer.writeheader()
            process_writer.writeheader()
            if options.diagnostico_cpu:
                raw_file = (base / "cpu_bruto.jsonl").open("x", encoding="utf-8")
                raw_file.write(json.dumps({"tipo": "baseline", "sistema": collector.raw_initial}) + "\n")
                raw_file.flush()
            while True:
                now = time.monotonic()
                if options.duracao is not None and now - started >= options.duracao:
                    metadata["estado"] = "duracao_concluida"
                    break
                remaining = max(0, deadline - now)
                if options.duracao is not None:
                    remaining = min(remaining, max(0, started + options.duracao - now))
                time.sleep(remaining)  # Cadência de observação, nunca simulação de carga.
                now = time.monotonic()
                if options.duracao is not None and now - started >= options.duracao:
                    metadata["estado"] = "duracao_concluida"
                    break
                system, rows = collector.sample(metadata["amostras"] + 1, now - started, now - last)
                system_writer.writerow(system)
                process_writer.writerows(rows)
                system_file.flush()
                process_file.flush()
                if raw_file:
                    raw_file.write(json.dumps(collector.last_raw) + "\n")
                    raw_file.flush()
                metadata["amostras"] += 1
                last = now
                deadline += options.intervalo
                # Não cria uma rajada de amostras se a coleta atrasar.
                if deadline <= time.monotonic():
                    deadline = time.monotonic() + options.intervalo
    except KeyboardInterrupt:
        metadata["estado"] = "ctrl_c"
    except PrincipalEncerrado:
        metadata["estado"] = "principal_encerrado"
    except Exception as error:
        metadata.update(estado="erro", erro=type(error).__name__)
        raise
    finally:
        if raw_file:
            raw_file.close()
        metadata.update(fim_utc=utc(), tempo_parede_s=time.monotonic() - started)
        salvar()
    return base


def main(argv=None):
    argument_parser = parser()
    options = argument_parser.parse_args(argv)
    if options.duracao is not None and options.duracao <= options.intervalo:
        argument_parser.error("A duração deve exceder o intervalo para produzir amostras.")
    if platform.system() != "Linux":
        argument_parser.error("Execute na VM Linux; testes Windows usam mocks.")
    try:
        collector = Coletor(options.pid, options.memoria_detalhada, options.diagnostico_cpu)
        executar(options, collector)
    except (psutil.Error, OSError, RuntimeError) as error:
        argument_parser.exit(1, f"Coleta não concluída: {type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
