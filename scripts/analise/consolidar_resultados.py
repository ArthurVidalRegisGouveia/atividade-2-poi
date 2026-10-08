"""Consolida repetições sem alterar entradas; somente biblioteca padrão."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import statistics


class DadosInvalidos(ValueError):
    pass


def instante(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise DadosInvalidos("Horário precisa de timezone explícito.")
    return result.astimezone(timezone.utc)


def numero(value):
    if value is None or str(value).strip() in ("", "N/A", "None"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def ler_csv(path, columns, warnings):
    if not path.is_file():
        warnings.append(f"Arquivo ausente: {path.name}")
        return []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            warnings.append(f"{path.name}: colunas ausentes: {', '.join(sorted(missing))}")
        return list(reader)


def ler_json(path, warnings):
    if not path.is_file():
        warnings.append(f"Arquivo ausente: {path.name}")
        return None
    with path.open(encoding="utf-8-sig") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise DadosInvalidos(f"{path.name}: objeto JSON esperado.")
    return data


def limites_console(path, offset):
    if offset is None or not path.is_file():
        return None
    zone = timezone(timedelta(minutes=offset))
    reset, stop = None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)\]", line)
        if not match:
            continue
        stamp = datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=zone).astimezone(timezone.utc)
        if "Resetting stats" in line:
            reset = stamp
        if "--run-time limit reached" in line:
            stop = stamp
            break
    return (reset, stop) if reset and stop and reset < stop else None


def janela(history, phase, users, directory, options, warnings):
    lower, upper = instante(phase["inicio_utc"]), instante(phase["fim_utc"])
    if bool(options.inicio_utc) != bool(options.fim_utc):
        raise DadosInvalidos("Informe inicio e fim UTC juntos.")
    if options.inicio_utc:
        start, end = instante(options.inicio_utc), instante(options.fim_utc)
        origin = "limites UTC declarados pelo operador"
    else:
        instrumentation = phase.get("instrumentacao", {})
        if not instrumentation and (directory / "medicao_instrumentacao.json").is_file():
            instrumentation = json.loads((directory / "medicao_instrumentacao.json").read_text(encoding="utf-8"))
        if instrumentation.get("usuarios_prontos_utc") and instrumentation.get("encerramento_inicio_utc"):
            limits = (instante(instrumentation["usuarios_prontos_utc"]), instante(instrumentation["encerramento_inicio_utc"]))
            origin = "marcos UTC diretos do Locust"
        else:
            limits = limites_console(directory / "medicao_console.txt", options.offset_log_minutos)
            origin = "reset e início do encerramento no console; offset declarado"
        if not limits:
            warnings.append("Janela não definida: informe offset do log com marcadores reset/stop ou inicio/fim UTC.")
            return None
        start, end = limits
    if not lower <= start < end <= upper:
        raise DadosInvalidos("Janela fora da fase de medição; confira timezone/relógio.")
    # CSV temporal fora de ordem não deve unir segmentos separados.
    history = sorted(history, key=lambda row: numero(row.get("Timestamp")) or float("-inf"))
    selected = []
    for row in history:
        if row.get("Name") != "Aggregated":
            continue
        timestamp = numero(row.get("Timestamp"))
        if timestamp is None:
            warnings.append("Histórico: Timestamp ausente/inválido.")
            continue
        stamp = datetime.fromtimestamp(timestamp, timezone.utc)
        if start < stamp < end:
            if numero(row.get("User Count")) != users:
                # Nunca une intervalos de carga separados por queda de usuários.
                if selected:
                    warnings.append("Queda de usuários: janela encerrada antes da queda.")
                    break
                continue
            selected.append((stamp, row))
    selected.sort(key=lambda item: item[0])
    if len(selected) < 2 or selected[0][0] >= selected[-1][0]:
        warnings.append("Histórico sem dois snapshots distintos em carga estável.")
        return None
    for (_, before), (_, after) in zip(selected, selected[1:]):
        for key in ("Total Request Count", "Total Failure Count"):
            a, b = numero(before.get(key)), numero(after.get(key))
            if a is not None and b is not None and b < a:
                raise DadosInvalidos("Contador diminuiu na janela: reset ou repetições misturadas.")
    return selected, origin


def estatisticas(rows, field, prefix, output, warnings):
    values = [numero(row.get(field)) for row in rows]
    valid = [value for value in values if value is not None]
    output[prefix + "_n"] = len(valid)
    output[prefix + "_media"] = statistics.fmean(valid) if valid else None
    output[prefix + "_max"] = max(valid) if valid else None
    if len(valid) != len(rows):
        warnings.append(f"{field}: {len(rows) - len(valid)} valores ausentes/inválidos na janela.")


def filtrar(rows, start, end, shift, interval_field, warnings):
    selected = []
    for row in rows:
        try:
            stamp = instante(row.get("utc", "")) + timedelta(seconds=shift)
        except ValueError:
            warnings.append("Monitor: UTC ausente/inválido.")
            continue
        interval = numero(row.get(interval_field))
        # Exige todo o intervalo de CPU dentro da janela. RAM usa as mesmas linhas.
        if interval is None or interval <= 0:
            continue
        if start <= stamp - timedelta(seconds=interval) and stamp <= end:
            selected.append(row)
    return selected


def correcao_relogio(metadata, options, output, warnings):
    check = metadata.get("verificacao_relogio") or {}
    if not isinstance(check, dict):
        check = {}
    probe = check.get("menor_incerteza") or {}
    if not isinstance(probe, dict):
        probe = {}
    offset = numero(probe.get("offset_estimado_s"))
    uncertainty = numero(probe.get("incerteza_meia_faixa_s"))
    same_target = str(check.get("url", "")).rstrip("/") == str(metadata.get("parametros", {}).get("url", "")).rstrip("/")
    valid = same_target and offset is not None and uncertainty is not None and uncertainty >= 0
    output.update(offset_linux_menos_windows_s=offset, incerteza_offset_s=uncertainty,
                  verificacao_relogio_utc=check.get("coletado_utc"))
    output["idade_sondagem_inicio_medicao_s"] = None
    if check.get("coletado_utc"):
        try:
            phase = next(p for p in metadata.get("fases", []) if p.get("fase") == "medicao")
            output["idade_sondagem_inicio_medicao_s"] = (instante(phase["inicio_utc"]) - instante(check["coletado_utc"])).total_seconds()
        except (ValueError, KeyError, StopIteration):
            warnings.append("Data da sondagem ausente/inválida: idade não verificável.")
    manual = options.correcao_monitor_s
    if manual is not None:
        shift, origin = manual, "manual (precedência sobre sondagem)"
    elif valid:
        shift, origin = -offset, "sondagem incorporada: UTC Windows = UTC Linux - offset"
        warnings.append("Correção estimada de relógio: assume offset constante; incerteza de rede não cobre deriva posterior.")
    else:
        shift, origin = 0, "sem sondagem válida; sem correção"
        warnings.append("Verificação de relógio ausente/inválida: alinhamento temporal não comprovado.")
    output.update(correcao_monitor_s=shift, origem_correcao_monitor=origin)
    return shift


def latencias_janela(directory, phase, options, start, end, output, warnings):
    """Nova coleta usa eventos concluídos; CSV antigo continua usando histórico."""
    path = directory / "medicao_latencias.csv"
    if not path.is_file():
        warnings.append("Latências individuais ausentes: p95 da janela indisponível; snapshots não recuperam percentis da janela.")
        return start, end, False
    instrumentation = phase.get("instrumentacao") or ler_json(directory / "medicao_instrumentacao.json", warnings) or {}
    report = instrumentation.get("latencias") or {}
    if report.get("completo") is not True:
        warnings.append("Registro de latências incompleto/não confirmado: média e p95 individuais indisponíveis.")
        return start, end, False
    if not instrumentation.get("usuarios_prontos_utc") or not instrumentation.get("encerramento_inicio_utc"):
        warnings.append("Latências sem marcos UTC da fase: janela exata não verificável.")
        return start, end, False
    # Arquivo novo permite usar os limites diretos, sem perder as bordas entre snapshots.
    if options.inicio_utc:
        lower, upper = instante(options.inicio_utc), instante(options.fim_utc)
    else:
        lower = instante(instrumentation["usuarios_prontos_utc"])
        upper = instante(instrumentation["encerramento_inicio_utc"])
    if not instante(phase["inicio_utc"]) <= lower < upper <= instante(phase["fim_utc"]):
        raise DadosInvalidos("Janela de latências fora da fase de medição.")
    if not instante(instrumentation["usuarios_prontos_utc"]) <= lower < upper <= instante(instrumentation["encerramento_inicio_utc"]):
        raise DadosInvalidos("Janela de latências inclui rampa ou encerramento.")
    if any("Queda de usuários" in warning for warning in warnings):
        lower, upper = start, end
        warnings.append("Latências recortadas ao segmento estável do histórico após queda de usuários.")
    values, failures, total = [], 0, 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"concluida_utc", "latencia_ms", "falha"}.issubset(reader.fieldnames or []):
            warnings.append("Latências: colunas obrigatórias ausentes.")
            return start, end, False
        for row in reader:
            total += 1
            if total > 1000000:
                warnings.append("Latências excedem limite de segurança da análise.")
                return start, end, False
            latency, failed = numero(row.get("latencia_ms")), numero(row.get("falha"))
            try:
                stamp = instante(row.get("concluida_utc", ""))
            except ValueError:
                stamp = None
            if stamp is None or latency is None or latency < 0 or failed not in (0, 1):
                warnings.append("Latências: registro inválido; métricas exatas não publicadas.")
                return start, end, False
            if lower < stamp <= upper:
                values.append(latency)
                failures += int(failed)
    if total != report.get("registros") or total > 1000000:
        warnings.append("Latências: contagem diverge dos metadados ou excede o limite; métricas não publicadas.")
        return start, end, False
    output.update(req_hist_janela=output["req_janela"], falhas_hist_janela=output["falhas_janela"],
                  duracao_hist_janela_s=output["duracao_janela_s"],
                  vazao_hist_calculada_janela_rps=output["vazao_calculada_janela_rps"],
                  latencia_media_hist_calculada_ms=output["latencia_media_calculada_janela_ms"],
                  inicio_hist_janela_utc=start.isoformat(), fim_hist_janela_utc=end.isoformat(),
                  req_janela=len(values), falhas_janela=failures, sucessos_janela=len(values) - failures,
                  inicio_janela_utc=lower.isoformat(), fim_janela_utc=upper.isoformat(),
                  duracao_janela_s=(upper - lower).total_seconds(), origem_janela="eventos individuais; limites UTC",
                  origem_latencias_janela="eventos request; inclui falhas com duração válida",
                  latencia_media_calculada_janela_ms=statistics.fmean(values) if values else None,
                  p95_janela_ms=sorted(values)[math.ceil(.95 * len(values)) - 1] if values else None,
                  latencias_janela_n=len(values))
    output["vazao_calculada_janela_rps"] = len(values) / output["duracao_janela_s"]
    if not values:
        warnings.append("Nenhuma latência na janela: média e p95 indisponíveis.")
    return lower, upper, True


def verificar_cpu_bruto(path, processes, start, end, shift, cpus, output, warnings):
    output.update(cpu_bruto_processos_n=0, cpu_bruto_processos_tempo_s=None,
                  cpu_bruto_processos_erro_max_pp=None, cpu_bruto_sistema_total_s=None,
                  cpu_bruto_sistema_ocupado_s=None)
    if not path.is_file():
        warnings.append("cpu_bruto.jsonl ausente: consistência dos deltas não verificável.")
        return
    lookup = {(row.get("amostra"), row["pid"], row["criado_epoch_s"]): row for row in processes}
    errors, times, totals, busy, elapsed = [], [], [], [], []
    previous = None
    with path.open(encoding="utf-8") as source:
        for line in source:
            try:
                record = json.loads(line)
                for process in record.get("processos", []):
                    key = (str(record.get("amostra")), str(process["pid"]), str(process["criado_epoch_s"]))
                    row = lookup.get(key)
                    before = process.get("anterior")
                    if row is None or before is None:
                        continue
                    current = process["cpu_times_s"]["user"] + process["cpu_times_s"]["system"]
                    delta, interval = current - before[0], process["monotonic_s"] - before[1]
                    rate, csv_interval = numero(row.get("cpu_uma_cpu_pct")), numero(row.get("cpu_intervalo_real_s"))
                    if numero(delta) is None or numero(interval) is None or delta < 0 or interval <= 0 or rate is None or csv_interval is None:
                        warnings.append("CPU bruta de processo: delta/intervalo inválido ou CSV ausente.")
                        continue
                    errors.append(abs(100 * delta / interval - rate))
                    times.append(delta)
                    if abs(csv_interval - interval) > 1e-6:
                        warnings.append("Intervalo monotônico bruto de processo diverge do CSV.")
                    normalized = numero(row.get("cpu_capacidade_vm_pct"))
                    if normalized is not None and cpus and abs(normalized - rate / cpus) > 1e-6:
                        warnings.append("CPU normalizada do processo diverge de CPU base / CPUs lógicas.")
                system = record["sistema"]
                counters = next(line for line in system["proc_stat_cpu_linhas"] if line.startswith("cpu "))
                ticks = [int(value) for value in counters.split()[1:9]]  # guest já incluído em user/nice.
                stamp = instante(system["utc"]) + timedelta(seconds=shift)
                mono = system["monotonic_after_s"]
                hz = system["clk_tck"]
                if previous is not None:
                    old_ticks, old_mono, old_hz = previous
                    interval = mono - old_mono
                    if interval > 0 and start <= stamp - timedelta(seconds=interval) and stamp <= end:
                        delta = [b - a for a, b in zip(old_ticks, ticks)]
                        if len(delta) == 8 and min(delta) >= 0 and hz == old_hz and hz > 0:
                            totals.append(sum(delta) / hz)
                            busy.append((sum(delta) - delta[3] - delta[4]) / hz)
                            elapsed.append(interval)
                        else:
                            warnings.append("/proc/stat: delta ou CLK_TCK inválido.")
                previous = ticks, mono, hz
            except (ValueError, KeyError, TypeError, StopIteration):
                warnings.append("Registro CPU bruto ausente/inválido; diagnóstico parcial.")
                previous = None
    output.update(cpu_bruto_processos_n=len(errors), cpu_bruto_processos_tempo_s=sum(times) if times else None,
                  cpu_bruto_processos_erro_max_pp=max(errors) if errors else None,
                  cpu_bruto_sistema_total_s=sum(totals) if totals else None,
                  cpu_bruto_sistema_ocupado_s=sum(busy) if busy else None,
                  cpu_bruto_sistema_intervalos_s=sum(elapsed) if elapsed else None)
    if len(errors) != len(processes):
        warnings.append("Diagnóstico bruto não cobre todos os registros de processos selecionados.")
    if errors and max(errors) > 1e-6:
        warnings.append("CPU dos processos inconsistente com os deltas brutos.")
    if elapsed and cpus and abs(sum(totals) - cpus * sum(elapsed)) > .05 * cpus * sum(elapsed):
        warnings.append("CPU global: contadores totais /proc/stat divergem da capacidade monotônica esperada (>5%); fontes não reconciliadas.")
    if busy and times and sum(times) > sum(busy) + max(.1, .05 * sum(busy)):
        warnings.append("CPU global: tempo ocupado /proc/stat menor que tempo da árvore em intervalos próximos; leituras sequenciais e fontes incompatíveis exigem investigação.")


def consolidar(directory, options):
    directory = Path(directory)
    warnings = []
    metadata = ler_json(directory / "parametros.json", warnings)
    if metadata is None:
        raise DadosInvalidos("parametros.json é obrigatório para identificar a repetição.")
    params = metadata.get("parametros", {})
    for key in ("cenario", "usuarios", "repeticao"):
        if params.get(key) is None:
            raise DadosInvalidos(f"Parâmetro obrigatório ausente: {key}")
    scenario, users, repeat = params["cenario"], params["usuarios"], params["repeticao"]
    if (not isinstance(scenario, str) or not scenario
            or type(users) is not int or users < 1 or type(repeat) is not int or repeat < 1):
        raise DadosInvalidos("Identificação experimental inválida.")
    if (directory.name != f"repeticao_{repeat:02d}" or directory.parent.name != f"usuarios_{users:02d}"
            or directory.parent.parent.name != scenario):
        raise DadosInvalidos("Cenário/demanda/repetição da pasta divergem dos metadados.")
    output = dict(cenario=scenario, usuarios=users, repeticao=repeat)
    for key in ("limite", "espera", "taxa", "duracao", "aquecimento", "url", "conexoes"):
        output[key] = params.get(key)
        if key not in params:
            warnings.append(f"Parâmetro ausente: {key}")
    output["locust_versao"] = metadata.get("locust")
    output["provisionamento_planejado"] = json.dumps(metadata.get("provisionamento_planejado"), ensure_ascii=False)
    for key in ("vcpus", "ram_gib", "workers"):
        output[key + "_planejado"] = (metadata.get("provisionamento_planejado") or {}).get(key)
    output["duracoes_incluem_rampa"] = metadata.get("duracoes_incluem_rampa")
    for recorded_phase in metadata.get("fases", []):
        name = recorded_phase.get("fase")
        if name in ("aquecimento", "medicao"):
            for boundary in ("inicio_utc", "fim_utc"):
                output[name + "_" + boundary] = recorded_phase.get(boundary)
            for boundary in ("usuarios_prontos_utc", "encerramento_inicio_utc"):
                output[name + "_" + boundary] = (recorded_phase.get("instrumentacao") or {}).get(boundary)
    phases = [phase for phase in metadata.get("fases", []) if phase.get("fase") == "medicao"]
    if len(phases) != 1:
        raise DadosInvalidos("É necessária exatamente uma fase medicao.")
    phase = phases[0]
    if "inicio_utc" not in phase or "fim_utc" not in phase:
        raise DadosInvalidos("Fase medicao sem inicio_utc/fim_utc.")
    wall = numero(phase.get("tempo_parede_s"))
    utc_duration = (instante(phase["fim_utc"]) - instante(phase["inicio_utc"])).total_seconds()
    output["desvio_utc_monotonico_locust_s"] = utc_duration - wall if wall is not None else None
    if wall is not None and abs(utc_duration - wall) > 1:
        warnings.append("Relógio Windows: diferença UTC/monotônico superior a 1 s.")
    if phase.get("estado") != "concluido" or phase.get("codigo_saida") != 0:
        warnings.append("Fase medicao incompleta ou com código de saída não zero.")
    summary_fields = {
        "Request Count": "req_snapshot", "Failure Count": "falhas_snapshot",
        "Average Response Time": "latencia_media_snapshot_ms", "95%": "p95_snapshot_ms",
        "Requests/s": "vazao_snapshot_rps",
    }
    stats = ler_csv(directory / "medicao_stats.csv", ["Name", *summary_fields], warnings)
    aggregate = [row for row in stats if row.get("Name") == "Aggregated"]
    if len(aggregate) != 1:
        warnings.append("Resumo Locust sem uma única linha Aggregated.")
    for source, target in summary_fields.items():
        output[target] = numero(aggregate[0].get(source)) if len(aggregate) == 1 else None
        if output[target] is None:
            warnings.append(f"Resumo Locust: {source} ausente/inválido.")
    warnings.append("Métricas snapshot são do CSV acumulado exportado, não necessariamente do encerramento nem da janela recortada.")
    for filename, fields in [("medicao_failures.csv", ["Occurrences"]),
                             ("medicao_exceptions.csv", ["Count"])]:
        ler_csv(directory / filename, fields, warnings)
    history = ler_csv(directory / "medicao_stats_history.csv", [
        "Name", "Timestamp", "User Count", "Total Request Count", "Total Failure Count",
        "Total Average Response Time",
    ], warnings)
    valid_window = janela(history, phase, users, directory, options, warnings)
    output.update(inicio_janela_utc=None, fim_janela_utc=None, duracao_janela_s=None,
                  req_janela=None, falhas_janela=None, sucessos_janela=None,
                  vazao_calculada_janela_rps=None, latencia_media_calculada_janela_ms=None,
                  p95_janela_ms=None, amostras_sistema=0, registros_processos=0)
    monitor_dir = options.monitoramento or directory / "monitoramento_linux"
    monitor_metadata = ler_json(monitor_dir / "metadados.json", warnings)
    if monitor_metadata is not None:
        if any(monitor_metadata.get(key) != output[key] for key in ("cenario", "usuarios", "repeticao")):
            raise DadosInvalidos("Metadados Linux pertencem a outro cenário/demanda/repetição.")
        output["cpus_logicas_observadas"] = monitor_metadata.get("cpus_logicas_observadas")
        output["ram_total_observada_bytes"] = monitor_metadata.get("ram_total_observada_bytes")
        output["condicoes_monitor"] = monitor_metadata.get("condicoes")
    system_fields = {
        "cpu_sistema_capacidade_pct": "cpu_vm_pct",
        "cpu_soma_uma_cpu_pct": "cpu_arvore_uma_cpu_pct",
        "cpu_soma_capacidade_vm_pct": "cpu_arvore_capacidade_pct",
        "ram_usada_psutil_bytes": "ram_usada_bytes", "ram_disponivel_bytes": "ram_disponivel_bytes",
        "ram_nao_disponivel_bytes": "ram_nao_disponivel_bytes", "rss_soma_bytes": "rss_soma_bytes",
        "uss_soma_bytes": "uss_soma_bytes", "pss_soma_bytes": "pss_soma_bytes",
    }
    systems = ler_csv(monitor_dir / "sistema.csv", ["utc", "intervalo_real_s", *system_fields], warnings)
    process_fields = {"cpu_uma_cpu_pct": "processo_cpu_uma_cpu_pct", "rss_bytes": "processo_rss_bytes"}
    processes = ler_csv(monitor_dir / "processos.csv", [
        "utc", "pid", "criado_epoch_s", "cpu_intervalo_real_s", *process_fields,
    ], warnings)
    residuals = []
    for row in systems:
        relative = numero(row.get("tempo_relativo_s"))
        if relative is not None:
            try:
                residuals.append(instante(row["utc"]).timestamp() - relative)
            except (ValueError, KeyError):
                pass
    output["variacao_utc_monotonico_linux_s"] = max(residuals) - min(residuals) if residuals else None
    if residuals and max(residuals) - min(residuals) > 1:
        warnings.append("Relógio Linux: possível salto/atraso; variação UTC/monotônico superior a 1 s.")
    shift = correcao_relogio(metadata, options, output, warnings)
    output["sincronizacao_declarada"] = options.relogios_sincronizados
    if not options.relogios_sincronizados:
        warnings.append("Sincronização dos relógios não confirmada: alinhamento UTC é provisório.")
    selected_system, selected_process = [], []
    if valid_window:
        selected, origin = valid_window
        start, end = selected[0][0], selected[-1][0]
        seconds = (end - start).total_seconds()
        output.update(inicio_janela_utc=start.isoformat(), fim_janela_utc=end.isoformat(),
                      duracao_janela_s=seconds, origem_janela=origin)
        first, last = selected[0][1], selected[-1][1]
        for source, target in [("Total Request Count", "req_janela"), ("Total Failure Count", "falhas_janela")]:
            a, b = numero(first.get(source)), numero(last.get(source))
            output[target] = b - a if a is not None and b is not None else None
            if output[target] is None:
                warnings.append(f"Histórico: {source} ausente na fronteira da janela.")
        count, failures = output["req_janela"], output["falhas_janela"]
        if count is not None:
            output["vazao_calculada_janela_rps"] = count / seconds
        if count is not None and failures is not None:
            if not 0 <= failures <= count:
                raise DadosInvalidos("Contadores de falhas/requisições inconsistentes.")
            output["sucessos_janela"] = count - failures
        if options.latencias_completas and count and count > 0:
            a, b = numero(first.get("Total Average Response Time")), numero(last.get("Total Average Response Time"))
            n0, n1 = numero(first.get("Total Request Count")), numero(last.get("Total Request Count"))
            if a is not None and b is not None:
                mean = (b * n1 - a * n0) / count
                if mean >= 0:
                    output["latencia_media_calculada_janela_ms"] = mean
        else:
            warnings.append("Média de latência da janela não calculada: exige declaração de latências completas.")
        start, end, exact = latencias_janela(directory, phase, options, start, end, output, warnings)
        if exact:
            warnings[:] = [warning for warning in warnings if not warning.startswith("Média de latência da janela não calculada")]
        if monitor_metadata is not None:
            selected_system = filtrar(systems, start, end, shift, "intervalo_real_s", warnings)
            selected_process = filtrar(processes, start, end, shift, "cpu_intervalo_real_s", warnings)
            verificar_cpu_bruto(monitor_dir / "cpu_bruto.jsonl", selected_process, start, end, shift,
                                numero(monitor_metadata.get("cpus_logicas_observadas")), output, warnings)
        if not selected_system:
            warnings.append("Sem amostras Linux válidas na janela; confira arquivos, cobertura e relógios.")
    output["amostras_sistema"], output["registros_processos"] = len(selected_system), len(selected_process)
    for source, prefix in system_fields.items():
        estatisticas(selected_system, source, prefix, output, warnings)
    for source, prefix in process_fields.items():
        estatisticas(selected_process, source, prefix, output, warnings)
    global_cpu, tree_cpu = output["cpu_vm_pct_media"], output["cpu_arvore_capacidade_pct_media"]
    if global_cpu is not None and tree_cpu is not None and tree_cpu > global_cpu + 5:
        warnings.append("CPU global menor que CPU da árvore (>5 pontos percentuais): métricas independentes; investigar contadores/intervalos, sem reconciliação automática.")
    output["processos_identidades"] = json.dumps(sorted({(row["pid"], row["criado_epoch_s"]) for row in selected_process}))
    output["avisos"] = " | ".join(dict.fromkeys(warnings))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entradas", nargs="+", type=Path, help="Pastas repeticao_NN; uma linha por repetição.")
    parser.add_argument("--saida", type=Path, required=True, help="Pasta nova e separada dos originais.")
    parser.add_argument("--monitoramento", type=Path, help="Pasta Linux externa; somente com uma entrada.")
    parser.add_argument("--inicio-utc")
    parser.add_argument("--fim-utc")
    parser.add_argument("--offset-log-minutos", type=int, help="UTC offset do console Windows; ex.: -180 para UTC-3.")
    parser.add_argument("--correcao-monitor-s", type=float, help="Override a somar ao UTC Linux; padrão usa -offset da sondagem incorporada.")
    parser.add_argument("--relogios-sincronizados", action="store_true", help="Confirmação externa, não verificação automática.")
    parser.add_argument("--latencias-completas", action="store_true", help="Declara duração disponível em todas as requisições para reconstruir média.")
    options = parser.parse_args(argv)
    if options.correcao_monitor_s is not None and not math.isfinite(options.correcao_monitor_s):
        parser.error("Correção de relógio deve ser finita.")
    if options.offset_log_minutos is not None and not -1439 <= options.offset_log_minutos <= 1439:
        parser.error("Offset deve estar entre -1439 e 1439 minutos.")
    if options.monitoramento and len(options.entradas) != 1:
        parser.error("Monitoramento externo exige exatamente uma entrada.")
    for path in options.entradas:
        if options.saida.resolve().is_relative_to(path.resolve()):
            parser.error("Saída precisa ficar fora das pastas originais.")
    if options.monitoramento and options.saida.resolve().is_relative_to(options.monitoramento.resolve()):
        parser.error("Saída precisa ficar fora da coleta Linux original.")
    try:
        rows = [consolidar(path, options) for path in options.entradas]
        keys = [(row["cenario"], row["usuarios"], row["repeticao"]) for row in rows]
        if len(keys) != len(set(keys)):
            raise DadosInvalidos("Repetição duplicada nas entradas.")
        options.saida.mkdir(parents=True, exist_ok=False)
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (options.saida / "consolidado.csv").open("x", encoding="utf-8", newline="") as source:
            writer = csv.DictWriter(source, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        with (options.saida / "resumo.txt").open("x", encoding="utf-8") as source:
            for row in rows:
                source.write(f"{row['cenario']} / {row['usuarios']} usuários / repetição {row['repeticao']}\n")
                for key, value in row.items():
                    source.write(f"  {key}: {value if value is not None else 'indisponível'}\n")
                source.write("\n")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Consolidação não concluída: {error}\n")
    print(f"Resumo salvo em {options.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
