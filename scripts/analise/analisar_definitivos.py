"""Estatística descritiva de uma campanha C1–C4, sem carga nem mistura de cenários."""

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analise.consolidar_resultados import numero, instante
from scripts.carga.executar_locust import SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
DEMANDAS = {"cpu": (1, 2, 5, 10), "memoria": (1, 2, 3), "io": (1, 2)}
# nome: (coluna do consolidado, divisor, unidade)
METRICAS = {
    "vazao_rps": ("vazao_calculada_janela_rps", 1, "req/s"),
    "latencia_media_ms": ("latencia_media_calculada_janela_ms", 1, "ms"),
    "p95_ms": ("p95_janela_ms", 1, "ms"),
    "falhas": ("falhas_janela", 1, "requisições"),
    "cpu_arvore_pct": ("cpu_arvore_capacidade_pct_media", 1, "% capacidade VM"),
    "cpu_global_pct": ("cpu_vm_pct_media", 1, "% capacidade VM; diagnóstico"),
    "ram_vm_mib": ("ram_usada_bytes_media", 1024**2, "MiB"),
    "ram_disponivel_mib": ("ram_disponivel_bytes_media", 1024**2, "MiB"),
    "rss_arvore_mib": ("rss_soma_bytes_media", 1024**2, "MiB; soma RSS"),
    "rss_pico_mib": ("rss_soma_bytes_max", 1024**2, "MiB; pico amostrado da soma RSS"),
    "uss_arvore_mib": ("uss_soma_bytes_media", 1024**2, "MiB; soma USS"),
    "pss_arvore_mib": ("pss_soma_bytes_media", 1024**2, "MiB; soma PSS"),
    "escrita_mib_s": ("escrita_bytes_s_media", 1024**2, "MiB/s; dispositivo VM"),
    "escrita_total_mib": ("escrita_bytes_delta_soma", 1024**2, "MiB; dispositivo VM"),
    "escritas_operacoes": ("escritas_delta_soma", 1, "operações; dispositivo VM"),
    "disco_ocupado_ms": ("ocupado_ms_delta_soma", 1, "ms; dispositivo VM"),
}
DISCO = {"escrita_mib_s", "escrita_total_mib", "escritas_operacoes", "disco_ocupado_ms"}
OBRIGATORIAS = {"vazao_rps", "latencia_media_ms", "p95_ms", "falhas", "cpu_arvore_pct", "ram_vm_mib", "rss_arvore_mib"}


def ler_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relativo(path):
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def estatistica(values):
    valid = [v for x in values if (v := numero(x)) is not None]
    return {"n_validos": len(valid), "ausentes": len(values) - len(valid),
            "media": statistics.fmean(valid) if valid else None,
            "desvio_padrao_amostral": statistics.stdev(valid) if len(valid) > 1 else None,
            "minimo": min(valid) if valid else None, "maximo": max(valid) if valid else None}


def cenario_unico(rows):
    scenarios = {r.get("cenario") for r in rows}
    if len(scenarios) != 1 or not scenarios <= set(SCENARIOS):
        raise ValueError("Índice/análise exige um único cenário válido C1, C2, C3 ou C4; cenários misturados não são aceitos.")
    return next(iter(scenarios))


def base_job(job):
    values = [job.get(k) for k in ("repeticao", "tentativa", "repeticao_logica")]
    if any(type(v) is not int for v in values):
        return None
    physical, attempt, logical = values
    if not 1 <= attempt <= 99 or logical not in (1, 2, 3):
        return None
    base = physical - 10 * (attempt - 1) - logical
    return base if base >= 1000 and base % 1000 == 0 else None


def base_campanha(entries, expected):
    # O plano inclui falhas/planejadas: elas identificam a campanha, não entram
    # nas estatísticas. Uma base exploratória parcial não substitui o plano completo.
    plans = defaultdict(set)
    for entry in entries:
        job = entry["job"]
        base = base_job(job)
        if base is not None:
            plans[base].add((job["aplicacao"], job["usuarios"], job["repeticao_logica"]))
    complete = {base for base, keys in plans.items()
                if {(app, u, r) for app, u in expected for r in (1, 2, 3)} <= keys}
    if len(complete) == 1:
        return complete.pop()
    if not complete and len(plans) == 1:
        return next(iter(plans))  # A contagem posterior explicita repetições ausentes.
    raise ValueError("Base da campanha ausente ou ambígua; confira a numeração e o plano do índice.")


def selecionar(indice, dispositivo="sda"):
    entries = ler_json(indice)
    if not isinstance(entries, list):
        raise ValueError("Índice deve ser uma lista.")
    rows, excluded, sources, seen = [], [], {relativo(indice): sha(indice)}, set()
    expected = {(app, u) for app, users in DEMANDAS.items() for u in users}
    cenario_unico([e["job"] for e in entries])
    base = base_campanha(entries, expected)
    for entry in entries:
        job = entry["job"]
        reason = None
        if entry.get("estado") != "concluída": reason = "estado não concluída"
        elif base_job(job) != base: reason = f"numeração inconsistente ou fora da base da campanha {base}"
        if reason:
            excluded.append({**job, "estado": entry.get("estado"), "motivo": reason})
            continue
        app, users, logical = job["aplicacao"], job["usuarios"], job["repeticao_logica"]
        if (app, users) not in expected or logical not in (1, 2, 3):
            raise ValueError(f"Combinação/repetição inesperada: {job}")
        key = (job["cenario"], app, users, logical)
        if key in seen:
            raise ValueError(f"Duas tentativas concluídas para a mesma repetição lógica: {key}")
        seen.add(key)
        manifest_path = Path(entry["manifesto"])
        # Somente arquivos do projeto; não procura execuções fora do índice.
        relativo(manifest_path)
        manifest = ler_json(manifest_path)
        if manifest.get("estado") != "concluída" or manifest.get("job") != job:
            raise ValueError(f"Índice e manifesto divergem: {manifest_path}")
        source = Path(manifest["analise"]) / "consolidado.csv"
        relativo(source)
        recorded_hash = manifest.get("artefatos_sha256", {}).get(str(source))
        if recorded_hash and recorded_hash != sha(source):
            raise ValueError(f"Consolidado diverge do hash registrado: {source}")
        with source.open(encoding="utf-8-sig", newline="") as f:
            records = list(csv.DictReader(f))
        if len(records) != 1:
            raise ValueError(f"Consolidado deve conter exatamente uma execução: {source}")
        raw = records[0]
        if any(str(raw.get(k)) != str(job[k]) for k in ("cenario", "aplicacao", "usuarios", "repeticao")):
            raise ValueError(f"Identidade do consolidado diverge: {source}")
        if raw.get("janela_carga_valida", "True") != "True":
            raise ValueError(f"Janela inválida: {source}")
        start, end = instante(raw["inicio_janela_utc"]), instante(raw["fim_janela_utc"])
        if start >= end or (numero(raw.get("req_janela")) or 0) <= 0 or (numero(raw.get("amostras_sistema")) or 0) <= 0:
            raise ValueError(f"Sem carga/cobertura válida: {source}")
        row = {**raw, "repeticao_logica": logical, "tentativa": job["tentativa"], "base_repeticao": base,
               "fonte_consolidado": relativo(source), "fonte_manifesto": relativo(manifest_path),
               "dispositivo_escrita": dispositivo if app == "io" else ""}
        warnings = list(dict.fromkeys((raw.get("avisos", "") + " | " + manifest.get("avisos", "")).split(" | ")))
        disks = json.loads(raw.get("discos_janela") or "{}")
        if not isinstance(disks, dict):
            raise ValueError(f"Contadores de disco inválidos: {source}")
        disk = disks.get(dispositivo, {}) if app == "io" else {}
        for name, (field, divisor, _) in METRICAS.items():
            value = numero(disk.get(field) if name in DISCO else raw.get(field))
            if value is not None and value < 0:
                raise ValueError(f"Métrica negativa {name}: {source}")
            row[name] = value / divisor if value is not None else None
            if value is None and (name not in DISCO or app == "io"):
                warnings.append(f"Métrica ausente: {name}; não imputada.")
        if any(row[name] is None for name in OBRIGATORIAS):
            raise ValueError(f"Métrica obrigatória ausente: {source}")
        if row["falhas"] > numero(raw["req_janela"]):
            raise ValueError(f"Falhas excedem requisições: {source}")
        row["avisos"] = " | ".join(w for w in dict.fromkeys(warnings) if w)
        rows.append(row)
        sources.update({relativo(manifest_path): sha(manifest_path), relativo(source): sha(source)})
    for app, users in sorted(expected):
        reps = {r["repeticao_logica"] for r in rows if r["aplicacao"] == app and int(r["usuarios"]) == users}
        if reps != {1, 2, 3}:
            raise ValueError(f"Exigidas três repetições válidas {app}/{users}; encontradas {sorted(reps)}.")
    return sorted(rows, key=lambda r: (r["aplicacao"], int(r["usuarios"]), r["repeticao_logica"])), excluded, sources


def agregar(rows):
    cenario_unico(rows)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cenario"], row["aplicacao"], int(row["usuarios"]))].append(row)
    result = []
    for (scenario, app, users), records in sorted(groups.items()):
        if len(records) != 3 or {r["repeticao_logica"] for r in records} != {1, 2, 3}:
            raise ValueError("Agregação exige exatamente três repetições lógicas distintas.")
        # Impede agregar cargas/provisionamentos diferentes sob a mesma identificação.
        for field in ("parametros_http", "configuracao_servidor_declarada", "conexoes", "espera",
                      "vcpus_planejado", "ram_gib_planejado", "workers_planejado", "duracao", "aquecimento"):
            if len({r.get(field) for r in records}) != 1:
                raise ValueError(f"Parâmetros divergentes dentro da combinação: {field}")
        for name, (field, _, unit) in METRICAS.items():
            if name in DISCO and app != "io": continue
            result.append({"cenario": scenario, "aplicacao": app, "usuarios": users,
                           "repeticoes": 3, "metrica": name, "unidade": unit,
                           "campo_origem": field, "dispositivo": records[0].get("dispositivo_escrita", "") if name in DISCO else "",
                           **estatistica([r[name] for r in records])})
    return result


def salvar_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def graficos(rows, aggregated, directory):
    scenario = cenario_unico(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    panels = {"vazao": [("vazao_rps", "Vazão (req/s)")],
              "latencia": [("latencia_media_ms", "Latência média (ms)"), ("p95_ms", "p95 por execução (ms)")],
              "cpu": [("cpu_arvore_pct", "CPU da árvore (% capacidade VM)")],
              "memoria": [("rss_arvore_mib", "Soma RSS (MiB)"), ("uss_arvore_mib", "Soma USS (MiB)"),
                          ("pss_arvore_mib", "Soma PSS (MiB)"), ("ram_vm_mib", "RAM usada VM (MiB)")],
              "escrita_disco": [("escrita_mib_s", "Escrita no dispositivo (MiB/s)")]}
    for filename, metrics in panels.items():
        apps = ["io"] if filename == "escrita_disco" else list(DEMANDAS)
        fig, axes = plt.subplots(1, len(apps), figsize=(5 * len(apps), 4.8), squeeze=False)
        for ax, app in zip(axes[0], apps):
            users = DEMANDAS[app]
            for name, label in metrics:
                data = [r for r in aggregated if r["aplicacao"] == app and r["metrica"] == name]
                available = [r for r in data if r["media"] is not None]
                if not available: continue
                ax.errorbar([r["usuarios"] for r in available], [r["media"] for r in available],
                            yerr=[r["desvio_padrao_amostral"] or 0 for r in available], marker="o", capsize=4, label=label)
            ax.set_title(f"{scenario} · {app} · n=3")
            ax.set_xticks(users)
            ax.set_xlabel("Usuários concorrentes (modelo fechado)")
            ax.set_ylabel(metrics[0][1] if len(metrics) == 1 else ("ms" if filename == "latencia" else "MiB"))
            ax.grid(alpha=.25)
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=8)
            ax.set_ylim(bottom=0)
        fig.suptitle("Média entre repetições ± desvio-padrão amostral; não é intervalo de confiança", fontsize=10)
        fig.tight_layout()
        fig.savefig(directory / f"{filename}.png", dpi=180)
        fig.savefig(directory / f"{filename}.svg")
        plt.close(fig)


def relatorio(rows, aggregated, excluded):
    scenario = cenario_unico(rows)
    bases = {r.get("base_repeticao") for r in rows}
    cpus = sorted({numero(r.get("cpus_logicas_observadas")) or numero(r.get("vcpus_planejado")) or SCENARIOS[scenario]["vcpus"] for r in rows})
    retention = sorted({str(r.get("retencao_servidor_s") or "ausente") for r in rows if r["aplicacao"] == "memoria"})
    def mean(app, users, metric):
        return next(r["media"] for r in aggregated if r["aplicacao"] == app and r["usuarios"] == users and r["metrica"] == metric)
    def fmt(value): return f"{value:.3f}" if value is not None else "ausente"
    lines = [f"# Análise definitiva — {scenario}", "", "## Seleção e método", "",
             "27 execuções concluídas; nove combinações; três repetições lógicas (1, 2, 3) por combinação. "
             f"Seleção restrita ao índice da campanha; base identificada nos registros: {', '.join(str(b) for b in bases)}. "
             "Numeração segue base + 10 × (tentativa − 1) + repetição lógica. Estados não concluídos e registros fora da base são excluídos.", "",
             "As unidades independentes são as repetições, com peso igual. Média = soma dos três valores / 3; "
             "desvio-padrão amostral usa divisor n−1. Mínimo/máximo são entre repetições, não entre requisições. "
             "O p95 agregado é a média dos p95 de cada execução, não o p95 de requisições reunidas. "
             "Falhas são contagens na janela útil; vazão = respostas concluídas / duração útil. "
             "Snapshots acumulados são preservados no CSV individual, mas não usados nessas estatísticas.", "",
             "Ausentes não são imputados; cada estatística informa n válido. Campos essenciais ausentes, "
             "repetições incompletas e tentativas concluídas ambíguas impedem a análise. USS/PSS/disco ausentes "
             "são explicitados; DP com menos de duas observações permanece ausente.", "",
             "## Resultados observados", "",
             "| Aplicação | Usuários | Vazão média (req/s) | Latência média (ms) | Média dos p95 (ms) | CPU árvore (%) | RSS (MiB) | Falhas médias |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for app, users in [(a,u) for a, demands in DEMANDAS.items() for u in demands]:
        vals = [mean(app, users, m) for m in ("vazao_rps", "latencia_media_ms", "p95_ms", "cpu_arvore_pct", "rss_arvore_mib", "falhas")]
        lines.append(f"| {app} | {users} | " + " | ".join(fmt(v) for v in vals) + " |")
    lines += ["", "Escrita no dispositivo explicitamente selecionado (não somada às partições):", "",
              "| Usuários I/O | Dispositivo | Escrita média (MiB/s) | Total médio nos intervalos (MiB) |",
              "|---:|---|---:|---:|"]
    for users in DEMANDAS["io"]:
        device = next(r["dispositivo_escrita"] for r in rows if r["aplicacao"] == "io" and int(r["usuarios"]) == users)
        lines.append(f"| {users} | {device} | {fmt(mean('io',users,'escrita_mib_s'))} | {fmt(mean('io',users,'escrita_total_mib'))} |")
    lines += ["", "## Análise interpretativa", "",
              f"CPU: a vazão passa de {fmt(mean('cpu',1,'vazao_rps'))} para {fmt(mean('cpu',2,'vazao_rps'))} req/s "
              f"entre um e dois usuários. Com cinco e dez, registra {fmt(mean('cpu',5,'vazao_rps'))} e "
              f"{fmt(mean('cpu',10,'vazao_rps'))} req/s. As latências médias correspondentes são "
              f"{fmt(mean('cpu',5,'latencia_media_ms'))} e {fmt(mean('cpu',10,'latencia_media_ms'))} ms. A CPU da árvore com dois usuários "
              f"é {fmt(mean('cpu',2,'cpu_arvore_pct'))}% da capacidade VM. Esses valores são observados; "
              "limitação por CPU e fila são hipóteses compatíveis quando alta utilização acompanha aumento de latência. Variações de CPU/vazão também podem envolver "
              "agendamento e sobrecarga; estes dados não isolam a causa nem demonstram saturação monotônica.", "",
              f"Memória: RSS médio passa de {fmt(mean('memoria',1,'rss_arvore_mib'))} a "
              f"{fmt(mean('memoria',3,'rss_arvore_mib'))} MiB entre um e três usuários. A vazão correspondente passa de "
              f"{fmt(mean('memoria',1,'vazao_rps'))} para {fmt(mean('memoria',3,'vazao_rps'))} req/s; CPU da árvore de "
              f"{fmt(mean('memoria',1,'cpu_arvore_pct'))}% para {fmt(mean('memoria',3,'cpu_arvore_pct'))}%. "
              f"Retenção declarada nos consolidados (segundos): {', '.join(retention)}. Quando habilitada, participa do tempo de resposta: serve à observação "
              "das alocações e não representa custo de acesso à RAM. Não há demonstração de esgotamento de RAM ou "
              "saturação de largura de banda da memória; o nome Memory-bound identifica o perfil implementado.", "",
              f"I/O: a vazão passa de {fmt(mean('io',1,'vazao_rps'))} para {fmt(mean('io',2,'vazao_rps'))} req/s; "
              f"latência média de {fmt(mean('io',1,'latencia_media_ms'))} para {fmt(mean('io',2,'latencia_media_ms'))} ms. "
              f"CPU da árvore passa de {fmt(mean('io',1,'cpu_arvore_pct'))}% para {fmt(mean('io',2,'cpu_arvore_pct'))}%. "
              "Se o ganho de vazão for limitado com baixa CPU, espera por I/O/sincronização é uma hipótese, mas esses valores não comprovam "
              "saturação do disco físico do Windows. Cache, fsync, disco virtual e outras atividades podem influenciar. "
              "Os contadores são do dispositivo da VM inteira; escrita lógica de arquivos não equivale a escrita física no host.", "",
              "## Limitações e avisos metodológicos", "",
              "CPU da árvore é soma dos percentuais dos processos dividida pelas CPUs lógicas; "
              f"100% representa a capacidade total da VM; CPUs lógicas observadas/declaradas: {', '.join(f'{c:g}' for c in cpus)}. CPU global permanece separada, sem reconciliar contadores inconsistentes. "
              "Médias de recursos são as médias amostradas que o consolidado fornece na janela útil.", "",
              "Soma RSS pode contar páginas compartilhadas mais de uma vez; não é memória privada. "
              "USS mede páginas privadas e PSS rateia páginas compartilhadas. RAM usada é do sistema inteiro. "
              "Picos são amostrados e podem perder eventos entre coletas. USS/PSS ausentes são explicitados por métrica e execução, não são zero.", "",
              "Correção de relógios já aplicada pelo consolidador: UTC Windows = UTC Linux − offset (Linux menos Windows). "
              "Não se aplica correção novamente. Sondagens não comprovam sincronização perfeita nem eliminam deriva. "
              "Avisos originais são preservados por execução em avisos.csv e nos dados individuais.", "",
              "Disco: um único dispositivo explicitamente selecionado, sem somar sda e sda5. "
              "A média de escrita é a média das taxas das amostras já consolidadas; total de bytes e operações cobre "
              "os intervalos selecionados, não necessariamente todos os limites UTC da carga. Não se atribui toda atividade à API.", "",
              "Três repetições permitem descrição da variabilidade, não conclusões causais ou testes de significância. "
              f"{scenario} sozinho não demonstra efeito do provisionamento comparado a outros cenários. Tentativas de recuperação "
              "podem envolver instrumentação revisada; confira os metadados antes de comparar execuções.", "",
              "## Auditoria de seleção", ""]
    for row in rows:
        lines.append(f"- {row['aplicacao']}/{row['usuarios']}: lógica {row['repeticao_logica']}, "
                     f"física R{row['repeticao']}, tentativa {row['tentativa']}.")
    for row in excluded:
        lines.append(f"- Excluída {row['aplicacao']}/{row['usuarios']}/R{row['repeticao']}: {row['motivo']}.")
    lines += ["", "## Gráficos", ""]
    for name in ("vazao", "latencia", "cpu", "memoria", "escrita_disco"):
        lines.append(f"![{name}]({name}.png)")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indice", type=Path, default=ROOT / "experimentos/resultados/orquestracao/definitivos_C4_01/indice.json")
    parser.add_argument("--saida", type=Path, help="Pasta nova; padrão analise_final/<cenário identificado>.")
    parser.add_argument("--dispositivo", default="sda", help="Um dispositivo apenas; nunca soma discos e partições.")
    args = parser.parse_args(argv)
    try:
        rows, excluded, sources = selecionar(args.indice, args.dispositivo)
        scenario = cenario_unico(rows)
        if args.saida is None:
            args.saida = ROOT / "experimentos/resultados/analise_final" / scenario
        relativo(args.saida)
        if not args.saida.resolve().is_relative_to((ROOT / "experimentos/resultados/analise_final").resolve()):
            raise ValueError("Saída deve ficar em analise_final, separada dos originais.")
        aggregated = agregar(rows)
        import matplotlib  # Verifica dependência antes de criar a saída.
        args.saida.mkdir(parents=True, exist_ok=False)
        salvar_csv(args.saida / "individuais.csv", rows)
        salvar_csv(args.saida / "agregados.csv", aggregated)
        warnings = [{"aplicacao": r["aplicacao"], "usuarios": r["usuarios"], "repeticao_logica": r["repeticao_logica"],
                     "repeticao": r["repeticao"], "aviso": w} for r in rows for w in r["avisos"].split(" | ") if w]
        salvar_csv(args.saida / "avisos.csv", warnings)
        (args.saida / "selecao.json").write_text(json.dumps({"criado_utc": datetime.now(timezone.utc).isoformat(),
            "indice": relativo(args.indice), "cenario": scenario, "base_repeticao": rows[0]["base_repeticao"],
            "fontes_sha256": sources, "dispositivo": args.dispositivo,
            "matplotlib": matplotlib.__version__, "selecionadas": len(rows), "excluidas": excluded}, ensure_ascii=False, indent=2), encoding="utf-8")
        graficos(rows, aggregated, args.saida)
        (args.saida / "relatorio.md").write_text(relatorio(rows, aggregated, excluded), encoding="utf-8")
    except (ValueError, KeyError, OSError, ImportError) as error:
        parser.exit(1, f"Análise não concluída: {error}\n")
    print(f"27 execuções / 9 combinações. Relatório: {args.saida / 'relatorio.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
