"""Comparação descritiva C1–C4 exclusivamente a partir de quatro agregados CSV."""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.analise.analisar_definitivos import DEMANDAS, METRICAS, DISCO, OBRIGATORIAS, estatistica, salvar_csv, sha
from scripts.carga.executar_locust import SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
PARES = (("C1", "C2", "aumento de RAM"), ("C3", "C4", "aumento de RAM"),
         ("C1", "C3", "mudança conjunta de vCPUs e workers"),
         ("C2", "C4", "mudança conjunta de vCPUs e workers"))
ESTATISTICAS = ("media", "desvio_padrao_amostral", "minimo", "maximo")


def valor(text):
    if text is None or str(text).strip() == "": return None
    number = float(text)
    if not math.isfinite(number): raise ValueError("Valor não finito na entrada")
    return number


def inteiro(text):
    number = valor(text)
    if number is None or not number.is_integer(): raise ValueError("Contagem inteira obrigatória")
    return int(number)


def caminho(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def carregar(fontes):
    if set(fontes) != set(SCENARIOS): raise ValueError("Exigidos quatro arquivos: C1, C2, C3 e C4")
    expected = {(app,u,m) for app, users in DEMANDAS.items() for u in users
                for m in METRICAS if app == "io" or m not in DISCO}
    rows, provenance = [], {}
    devices = set()
    columns = {"cenario", "aplicacao", "usuarios", "repeticoes", "metrica", "unidade", "campo_origem",
               "dispositivo", "n_validos", "ausentes", *ESTATISTICAS}
    for scenario in SCENARIOS:
        path = fontes[scenario]
        relative = caminho(path)
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if columns - set(reader.fieldnames or []): raise ValueError(f"Colunas ausentes: {path}")
            records = list(reader)
        seen = set()
        for record in records:
            row = dict(record)
            if row["cenario"] != scenario: raise ValueError(f"Cenário incorreto em {path}")
            row["usuarios"] = inteiro(row["usuarios"])
            key = (row["aplicacao"],row["usuarios"],row["metrica"])
            if key not in expected or key in seen: raise ValueError(f"Combinação desconhecida ou duplicada: {key}")
            seen.add(key)
            metric = row["metrica"]
            if (row["campo_origem"],row["unidade"]) != (METRICAS[metric][0],METRICAS[metric][2]):
                raise ValueError(f"Origem/unidade divergente: {key}")
            row["repeticoes"] = inteiro(row["repeticoes"])
            row["n_validos"], row["ausentes"] = inteiro(row["n_validos"]), inteiro(row["ausentes"])
            n = row["n_validos"]
            if row["repeticoes"] != 3 or not 0 <= n <= 3 or row["ausentes"] != 3-n:
                raise ValueError(f"Repetições/contagens inconsistentes: {key}")
            if metric in OBRIGATORIAS and n != 3: raise ValueError(f"Métrica essencial sem três valores válidos: {key}")
            for field in ESTATISTICAS:
                row[field] = valor(row[field])
                if row[field] is not None and row[field] < 0: raise ValueError(f"Estatística negativa: {key}")
            mean, sd, low, high = (row[k] for k in ESTATISTICAS)
            if n == 0:
                if any(row[k] is not None for k in ESTATISTICAS): raise ValueError(f"Ausência com estatística preenchida: {key}")
            else:
                if mean is None or low is None or high is None or not low <= mean <= high:
                    raise ValueError(f"Média/extremos inconsistentes: {key}")
                if (n == 1 and sd is not None) or (n > 1 and sd is None): raise ValueError(f"DP incompatível com n: {key}")
                # Checagem algébrica dos resumos, não reconstrução publicada de repetições.
                values = [mean] if n == 1 else ([low, high] if n == 2 else [low, 3*mean-low-high, high])
                if any(not math.isfinite(v) or (v < low and not math.isclose(v,low,abs_tol=1e-9))
                       or (v > high and not math.isclose(v,high,abs_tol=1e-9)) for v in values):
                    raise ValueError(f"Resumo impossível para n={n}: {key}")
                check = estatistica(values)
                for field in ESTATISTICAS:
                    if row[field] is not None and not math.isclose(row[field],check[field],rel_tol=1e-7,abs_tol=1e-9):
                        raise ValueError(f"Estatística inconsistente ({field}): {key}")
            if metric in DISCO:
                if not row["dispositivo"]: raise ValueError("Métrica de disco sem dispositivo identificado")
                devices.add(row["dispositivo"])
            elif row["dispositivo"]: raise ValueError("Dispositivo preenchido em métrica não relacionada a disco")
            row.update(fonte=relative, **SCENARIOS[scenario])
            rows.append(row)
        if seen != expected: raise ValueError(f"Combinações/métricas ausentes em {scenario}: {sorted(expected-seen)}")
        provenance[relative] = sha(path)
    if len(devices) != 1: raise ValueError("Dispositivos de disco diferentes entre entradas; não serão somados ou equiparados")
    return rows, provenance


def diferenca(base, target):
    if base is None or target is None:
        return dict(diferenca_absoluta=None, diferenca_percentual=None, motivo="métrica ausente")
    delta = target-base
    if not math.isfinite(delta): return dict(diferenca_absoluta=None,diferenca_percentual=None,motivo="diferença não finita")
    if base == 0: return dict(diferenca_absoluta=delta,diferenca_percentual=None,motivo="denominador zero")
    percent = delta/base*100
    return dict(diferenca_absoluta=delta, diferenca_percentual=percent if math.isfinite(percent) else None,
                motivo="" if math.isfinite(percent) else "percentual não finito")


def comparar(rows):
    lookup = {(r["cenario"],r["aplicacao"],r["usuarios"],r["metrica"]):r for r in rows}
    tables, differences = [], []
    keys = sorted({(r["aplicacao"],r["usuarios"],r["metrica"]) for r in rows})
    for app, users, metric in keys:
        source = lookup[("C1",app,users,metric)]
        table = dict(aplicacao=app,usuarios=users,metrica=metric,unidade=source["unidade"],dispositivo=source["dispositivo"])
        for scenario in SCENARIOS:
            row = lookup[(scenario,app,users,metric)]
            for field in (*ESTATISTICAS,"n_validos","ausentes"):
                table[scenario+"_"+field] = row[field]
        tables.append(table)
        for before, after, change in PARES:
            a,b = lookup[(before,app,users,metric)],lookup[(after,app,users,metric)]
            differences.append(dict(aplicacao=app,usuarios=users,metrica=metric,unidade=source["unidade"],
                unidade_diferenca="pontos percentuais da capacidade VM" if metric.endswith("_pct") else source["unidade"],
                dispositivo=source["dispositivo"],cenario_base=before,cenario_comparado=after,alteracao=change,
                media_base=a["media"],media_comparada=b["media"],n_base=a["n_validos"],n_comparado=b["n_validos"],
                **diferenca(a["media"],b["media"])))
    return tables,differences


def graficos(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lookup = {(r["cenario"],r["aplicacao"],r["usuarios"],r["metrica"]):r for r in rows}
    panels = {"vazao":["vazao_rps"], "latencia":["latencia_media_ms","p95_ms"], "cpu":["cpu_arvore_pct"],
              "memoria":["rss_arvore_mib","uss_arvore_mib","pss_arvore_mib","ram_vm_mib"], "falhas":["falhas"]}
    for app, users in DEMANDAS.items():
        groups = dict(panels)
        if app == "io": groups["disco"] = ["escrita_mib_s","escrita_total_mib","escritas_operacoes","disco_ocupado_ms"]
        for name, metrics in groups.items():
            ncols = 2 if len(metrics)>1 else 1
            nrows = math.ceil(len(metrics)/ncols)
            fig,axes = plt.subplots(nrows,ncols,figsize=(6*ncols,4.4*nrows),squeeze=False)
            for ax,metric in zip(axes.flat,metrics):
                present = False
                for i,scenario in enumerate(SCENARIOS):
                    data = [lookup[(scenario,app,u,metric)] for u in users]
                    valid = [(j,r) for j,r in enumerate(data) if r["media"] is not None]
                    xs = [j + (i-1.5)*.18 for j,r in valid]
                    label = f"{scenario} ({SCENARIOS[scenario]['vcpus']} vCPU, {SCENARIOS[scenario]['ram_gib']} GiB, {SCENARIOS[scenario]['workers']} worker)"
                    ax.bar(xs,[r["media"] for j,r in valid],width=.17,label=label,color=f"C{i}")
                    for x,(j,r) in zip(xs,valid):
                        if r["desvio_padrao_amostral"] is not None:
                            ax.errorbar(x,r["media"],yerr=r["desvio_padrao_amostral"],fmt="none",ecolor="black",capsize=3)
                    present = present or bool(valid)
                if not present: ax.text(.5,.5,"Métrica ausente nos quatro cenários",ha="center",transform=ax.transAxes)
                ax.set_xticks(range(len(users)),users)
                ax.set_xlabel("Usuários concorrentes (modelo fechado)")
                ax.set_title(metric)
                ax.set_ylabel(METRICAS[metric][2])
                ax.set_ylim(bottom=0)
                if ax.get_ylim()[1] <= .06: ax.set_ylim(0,1)
                ax.grid(axis="y",alpha=.2)
            handles,labels = axes.flat[0].get_legend_handles_labels()
            fig.legend(handles,labels,loc="lower center",ncol=2,fontsize=8)
            fig.suptitle(f"{app} · média ± DP amostral; n válido por métrica no CSV\nBarras de erro não são intervalos de confiança",fontsize=11)
            fig.tight_layout(rect=(0,.1,1,.91))
            for extension in ("png","svg"): fig.savefig(output/f"{app}_{name}.{extension}",dpi=180)
            plt.close(fig)


def relatorio(rows,tables,differences):
    lookup = {(r["cenario"],r["aplicacao"],r["usuarios"],r["metrica"]):r for r in rows}
    def mean(c,a,u,m): return lookup[(c,a,u,m)]["media"]
    def fmt(v): return "ausente" if v is None else f"{v:.3f}"
    def cell(c,a,u,m):
        r = lookup[(c,a,u,m)]
        return "ausente (n=0)" if r["media"] is None else f"{fmt(r['media'])} ± {fmt(r['desvio_padrao_amostral'])} (n={r['n_validos']})"
    lines = ["# Comparação definitiva C1–C4", "", "## Fontes e metodologia", "",
        "Fontes exclusivas: os quatro agregados.csv individuais. São conferidas 116 linhas por cenário, "
        "nove combinações e três repetições declaradas por combinação (27 por cenário). "
        "Não são reestimadas as estatísticas das execuções, reunidas latências individuais ou incluídas tentativas inválidas.", "",
        "| Cenário | vCPUs | RAM (GiB) | Workers |", "|---|---:|---:|---:|"]
    for c,config in SCENARIOS.items(): lines.append(f"| {c} | {config['vcpus']} | {config['ram_gib']} | {config['workers']} |")
    lines += ["", "Configurações acima são as informadas para o experimento, não medições adicionais. Média e DP amostral "
        "são reproduzidos das fontes; n válido é mostrado por métrica. Ausentes permanecem ausentes. "
        "A média dos p95 das repetições não é o p95 de requisições reunidas. As barras de erro não são intervalos de confiança. "
        "A consistência algébrica de média/extremos/DP é verificada sem publicar repetições reconstruídas.", "",
        "Diferença absoluta = média comparada − média base; percentual = 100 × diferença / média base. "
        "Não há percentual quando a base é zero ou algum valor está ausente. Para CPU, a diferença absoluta é "
        "em pontos percentuais; o percentual relativo é outra grandeza. Não são calculados testes de significância "
        "nem intervalos de confiança de diferenças a partir dos resumos.", "", "## Tabelas comparativas", ""]
    for metric in METRICAS:
        lines += [f"### {metric} — {METRICAS[metric][2]}", "",
            "| Aplicação | Usuários | C1: média ± DP | C2: média ± DP | C3: média ± DP | C4: média ± DP |",
            "|---|---:|---|---|---|---|"]
        for row in tables:
            if row["metrica"] == metric:
                a,u = row["aplicacao"],row["usuarios"]
                lines.append(f"| {a} | {u} | "+" | ".join(cell(c,a,u,metric) for c in SCENARIOS)+" |")
        lines.append("")
    lines += ["## Pares de provisionamento", "",
        "C1→C2 e C3→C4 associam o aumento de RAM a resultados mantendo vCPUs/workers constantes. "
        "C1→C3 e C2→C4 mudam vCPUs e workers conjuntamente, com RAM constante; não isolam efeitos de cada fator.", ""]
    for before,after,change in PARES:
        lines += [f"### {before} → {after}: {change}", "",
            "| Aplicação | Usuários | Δ vazão (req/s) | Δ vazão (%) | Δ latência (ms) | Δ latência (%) |",
            "|---|---:|---:|---:|---:|---:|"]
        for a,users in DEMANDAS.items():
            for u in users:
                records = [next(r for r in differences if (r['cenario_base'],r['cenario_comparado'],r['aplicacao'],r['usuarios'],r['metrica'])==(before,after,a,u,m)) for m in ('vazao_rps','latencia_media_ms')]
                lines.append(f"| {a} | {u} | "+" | ".join(fmt(r[k]) for r in records for k in ('diferenca_absoluta','diferenca_percentual'))+" |")
        lines.append("")
    lines += ["## Interpretação dos padrões observados", "", "### CPU e saturação", ""]
    for c in SCENARIOS:
        lines.append(f"- {c}: vazão de {fmt(mean(c,'cpu',1,'vazao_rps'))} req/s (1 usuário), "
            f"{fmt(mean(c,'cpu',2,'vazao_rps'))} (2) e {fmt(mean(c,'cpu',10,'vazao_rps'))} (10). "
            f"CPU da árvore com 2 usuários: {fmt(mean(c,'cpu',2,'cpu_arvore_pct'))}% da capacidade; "
            f"latência média de {fmt(mean(c,'cpu',1,'latencia_media_ms'))} para {fmt(mean(c,'cpu',10,'latencia_media_ms'))} ms entre 1 e 10 usuários.")
    lines += ["", "CPU próxima da capacidade, vazão que deixa de crescer e latência crescente são compatíveis com "
        "saturação e formação de filas. Nos cenários de duas vCPUs, observe também a queda de utilização/vazão "
        "nas maiores demandas: esses dados não isolam mecanismos de agendamento ou sobrecarga. "
        "A mudança conjunta de workers e vCPUs impede atribuir o ganho somente ao processador. "
        "CPU normalizada de 100% em C1/C2 representa uma vCPU, em C3/C4 duas; percentuais iguais não equivalem "
        "a tempo de CPU absoluto igual. CPU global está nas tabelas separadamente; inconsistências conhecidas "
        "dos contadores globais impedem reconciliá-la automaticamente com a árvore.", "", "### Memória", ""]
    for c in SCENARIOS:
        lines.append(f"- {c}: na aplicação memória, RSS de {fmt(mean(c,'memoria',1,'rss_arvore_mib'))} "
            f"para {fmt(mean(c,'memoria',3,'rss_arvore_mib'))} MiB entre 1 e 3 usuários; vazão de "
            f"{fmt(mean(c,'memoria',1,'vazao_rps'))} para {fmt(mean(c,'memoria',3,'vazao_rps'))} req/s.")
    lines += ["", "Soma RSS inclui páginas compartilhadas e não mede memória privada. USS/PSS disponíveis "
        "complementam a interpretação; aumentar workers pode aumentar o consumo base dos processos. RAM usada "
        "é do sistema inteiro. O nome Memory-bound descreve o perfil da API; estes resumos não comprovam "
        "saturação de largura de banda de RAM nem ausência/presença de swap. A retenção temporal pode dominar "
        "a latência e não deve ser interpretada como tempo de acesso à memória; seus parâmetros não podem ser "
        "revalidados exclusivamente pelos agregados. Não há melhora de RAM universal a presumir nos pares.", "", "### I/O", ""]
    for c in SCENARIOS:
        lines.append(f"- {c}: vazão I/O de {fmt(mean(c,'io',1,'vazao_rps'))} para {fmt(mean(c,'io',2,'vazao_rps'))} req/s "
            f"entre 1 e 2 usuários; latência de {fmt(mean(c,'io',1,'latencia_media_ms'))} para "
            f"{fmt(mean(c,'io',2,'latencia_media_ms'))} ms; escrita média com 2 usuários: "
            f"{fmt(mean(c,'io',2,'escrita_mib_s'))} MiB/s.")
    device = next(r['dispositivo'] for r in rows if r['metrica'] in DISCO)
    lines += ["", f"Contadores de disco referem-se somente a `{device}`, nunca à soma disco+partição. "
        "Ganhos limitados de vazão com maior latência e baixa CPU são compatíveis com espera de I/O, "
        "mas não demonstram saturação física do armazenamento do Windows. O dispositivo é da VM inteira; "
        "cache, fsync e a camada de disco virtual influenciam resultados. Bytes de arquivos e bytes do dispositivo "
        "não são intercambiáveis; nenhum contador é atribuído integralmente à API.", "", "## Limitações metodológicas", "",
        "- Houve uma atualização do Ubuntu durante a campanha, conforme o contexto do experimento. As fontes "
        "não contêm data/versão suficientes para quantificar seu efeito; ele permanece possível fator de confusão.",
        "- Tentativas inválidas foram recuperadas em novas execuções físicas. Mudanças de horário, sistema e "
        "instrumentação podem influenciar a comparação; os agregados não contêm a sequência completa dessas recuperações.",
        "- São três repetições independentes por combinação conforme a coleta declarada. Os CSVs agregados "
        "permitem verificar contagens/resumos, mas não auditar identidades, independência real ou seleção de tentativas novamente.",
        "- Offset e incerteza dos relógios e as janelas UTC não constam nesses CSVs. Nenhuma nova sincronização "
        "é presumida, nenhum alinhamento é refeito e nenhum aviso anterior de CPU global é considerado resolvido.",
        "- Parâmetros das APIs, ordem de coleta, versões, retenção e fsync não podem ser conferidos nessas fontes. "
        "A comparabilidade pressupõe o protocolo declarado; não foi comprovada novamente por acesso a outras fontes.",
        "- DP descreve variabilidade entre repetições; sobreposição ou separação das barras não constitui teste "
        "de significância. Ausências/contagens parciais são explícitas; nenhuma imputação foi realizada.", "", "## Conclusões", "",
        "Os números observados permitem comparar desempenho e variabilidade no protocolo adotado. "
        "O padrão CPU diferencia capacidade sob concorrência; RSS caracteriza custo de memória com demanda; "
        "I/O exige considerar espera, sincronização e virtualização. As tabelas de diferenças registram tanto "
        "ganhos quanto perdas, sem concluir benefício causal universal do aumento de RAM ou isolar vCPUs de workers. "
        "A atualização do sistema e as recuperações limitam conclusões causais definitivas.", "", "## Gráficos", ""]
    for app in DEMANDAS:
        for group in ('vazao','latencia','cpu','memoria','falhas',*(['disco'] if app=='io' else [])):
            lines += [f"### {app}: {group}", "", f"![{app} {group}]({app}_{group}.png)", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entradas",type=Path,default=ROOT/"experimentos/resultados/analise_final",help="Raiz com C1–C4/agregados.csv")
    parser.add_argument("--saida",type=Path,default=ROOT/"experimentos/resultados/analise_final/comparativo_C1_C4")
    args = parser.parse_args(argv)
    try:
        caminho(args.saida)
        if not args.saida.resolve().is_relative_to((ROOT/"experimentos/resultados/analise_final").resolve()):
            raise ValueError("Saída deve ficar em analise_final, separada dos cenários")
        fontes = {c:args.entradas/c/"agregados.csv" for c in SCENARIOS}
        if any(args.saida.resolve().is_relative_to(p.parent.resolve()) for p in fontes.values()):
            raise ValueError("Saída não pode estar dentro das fontes individuais")
        if args.saida.exists(): raise ValueError("Saída já existe; nenhuma sobrescrita permitida")
        rows,sources = carregar(fontes)
        tables,differences = comparar(rows)
        import matplotlib
        args.saida.mkdir(parents=True,exist_ok=False)
        salvar_csv(args.saida/"comparativos.csv",rows)
        salvar_csv(args.saida/"tabelas.csv",tables)
        salvar_csv(args.saida/"diferencas.csv",differences)
        graficos(rows,args.saida)
        (args.saida/"relatorio.md").write_text(relatorio(rows,tables,differences),encoding="utf-8")
        (args.saida/"fontes.json").write_text(json.dumps(dict(criado_utc=datetime.now(timezone.utc).isoformat(),
            fontes_sha256=sources,configuracoes_declaradas=SCENARIOS,pares=PARES,matplotlib=matplotlib.__version__,
            estatistica="média e DP amostral das fontes, sem reestimar; diferenças entre médias; não IC"),ensure_ascii=False,indent=2),encoding="utf-8")
    except (ValueError,KeyError,OSError,ImportError) as error:
        parser.exit(1,f"Comparação não concluída: {error}\n")
    print(f"Comparação: {args.saida/'relatorio.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
