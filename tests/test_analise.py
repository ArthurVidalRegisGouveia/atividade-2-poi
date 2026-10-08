"""Fixtures pequenas: sem tráfego, sem resultados reais nem bibliotecas extras."""

import csv
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from scripts.analise import consolidar_resultados as analysis


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as source:
        writer = csv.DictWriter(source, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def options(**kwargs):
    values = dict(monitoramento=None, inicio_utc="2026-10-08T16:00:01Z",
                  fim_utc="2026-10-08T16:00:09Z", offset_log_minutos=None,
                  correcao_monitor_s=0, relogios_sincronizados=True, latencias_completas=True)
    values.update(kwargs)
    return SimpleNamespace(**values)


@pytest.fixture
def run(tmp_path):
    directory = tmp_path / "C1/usuarios_01/repeticao_01"
    monitor = directory / "monitoramento_linux"
    monitor.mkdir(parents=True)
    metadata = {"parametros": {"cenario": "C1", "usuarios": 1, "repeticao": 1,
                              "limite": 100000, "espera": 1, "taxa": 1, "duracao": 10,
                              "aquecimento": 5, "url": "http://localhost:8001"},
                "fases": [{"fase": "aquecimento", "inicio_utc": "2026-10-08T15:59:50Z"},
                          {"fase": "medicao", "inicio_utc": "2026-10-08T16:00:00Z",
                           "fim_utc": "2026-10-08T16:00:12Z", "estado": "concluido", "codigo_saida": 0}]}
    (directory / "parametros.json").write_text(json.dumps(metadata), encoding="utf-8")
    write_csv(directory / "medicao_stats.csv", [{"Name": "Aggregated", "Request Count": 20,
              "Failure Count": 2, "Average Response Time": 50, "95%": 90, "Requests/s": 2}])
    base = int(datetime(2026, 10, 8, 16, tzinfo=timezone.utc).timestamp())
    history = [{"Name": "Aggregated", "Timestamp": base + t, "User Count": users,
                "Total Request Count": count, "Total Failure Count": failed,
                "Total Average Response Time": mean}
               for t, users, count, failed, mean in [(0, 0, 0, 0, 0), (2, 1, 2, 0, 10),
                                                    (5, 1, 5, 1, 22), (8, 1, 8, 1, 25),
                                                    (10, 0, 20, 2, 50)]]
    write_csv(directory / "medicao_stats_history.csv", history)
    (monitor / "metadados.json").write_text(json.dumps({"cenario": "C1", "usuarios": 1,
                                                       "repeticao": 1}), encoding="utf-8")
    systems = [{"utc": f"2026-10-08T16:00:{t:02d}Z", "intervalo_real_s": 1,
                "tempo_relativo_s": t, "cpu_sistema_capacidade_pct": cpu,
                "cpu_soma_uma_cpu_pct": cpu, "cpu_soma_capacidade_vm_pct": cpu,
                "ram_usada_psutil_bytes": 100 + cpu, "ram_disponivel_bytes": 1000,
                "ram_nao_disponivel_bytes": 200, "rss_soma_bytes": 50 + cpu,
                "uss_soma_bytes": "", "pss_soma_bytes": ""}
               for t, cpu in [(1, 99), (2, 99), (3, 20), (5, 40), (8, 60), (9, 99)]]
    write_csv(monitor / "sistema.csv", systems)
    processes = [{"utc": row["utc"], "cpu_intervalo_real_s": 1, "pid": 42,
                  "criado_epoch_s": 1, "cpu_uma_cpu_pct": row["cpu_sistema_capacidade_pct"],
                  "rss_bytes": row["rss_soma_bytes"]} for row in systems]
    write_csv(monitor / "processos.csv", processes)
    return directory


def test_janela_contadores_latencia_e_recursos(run):
    row = analysis.consolidar(run, options())
    assert row["req_janela"] == 6
    assert row["falhas_janela"] == 1
    assert row["sucessos_janela"] == 5
    assert row["vazao_calculada_janela_rps"] == 1  # 6 requisições / 6 s.
    assert row["latencia_media_calculada_janela_ms"] == 30  # (8*25 - 2*10)/6.
    assert row["p95_janela_ms"] is None
    assert row["p95_snapshot_ms"] == 90
    assert row["vazao_snapshot_rps"] == 2
    assert row["cpu_vm_pct_media"] == 40
    assert row["cpu_vm_pct_max"] == 60
    assert row["rss_soma_bytes_media"] == 90
    assert row["amostras_sistema"] == 3
    assert row["registros_processos"] == 3


def test_console_timezone_e_exclusao_aquecimento(run):
    (run / "medicao_console.txt").write_text(
        "[2026-10-08 13:00:01,000] INFO Resetting stats\n"
        "[2026-10-08 13:00:09,000] INFO --run-time limit reached\n", encoding="utf-8")
    row = analysis.consolidar(run, options(inicio_utc=None, fim_utc=None, offset_log_minutos=-180))
    assert row["inicio_janela_utc"] == "2026-10-08T16:00:02+00:00"
    assert row["fim_janela_utc"] == "2026-10-08T16:00:08+00:00"
    assert row["cpu_vm_pct_media"] == 40


def test_sem_limites_nao_inventa_janela(run):
    row = analysis.consolidar(run, options(inicio_utc=None, fim_utc=None))
    assert row["cpu_vm_pct_media"] is None
    assert row["req_janela"] is None
    assert "Janela não definida" in row["avisos"]


@pytest.mark.parametrize("target", ["locust", "monitor"])
def test_associacao_repeticao(run, target):
    path = run / ("parametros.json" if target == "locust" else "monitoramento_linux/metadados.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    (data["parametros"] if target == "locust" else data)["repeticao"] = 2
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(analysis.DadosInvalidos):
        analysis.consolidar(run, options())


def test_campos_ausentes(run):
    write_csv(run / "medicao_stats.csv", [{"Name": "Aggregated", "Request Count": 8}])
    row = analysis.consolidar(run, options(latencias_completas=False))
    assert row["p95_snapshot_ms"] is None
    assert row["latencia_media_calculada_janela_ms"] is None
    assert row["uss_soma_bytes_media"] is None
    assert "colunas ausentes" in row["avisos"]
    assert "valores ausentes" in row["avisos"]


def test_monitor_ausente(run, tmp_path):
    row = analysis.consolidar(run, options(monitoramento=tmp_path / "ausente"))
    assert row["req_janela"] == 6
    assert row["amostras_sistema"] == 0
    assert "Arquivo ausente: sistema.csv" in row["avisos"]


def test_correcao_relogio(run):
    row = analysis.consolidar(run, options(correcao_monitor_s=2, relogios_sincronizados=False))
    # Após somar 2 s, timestamps originais 1,2,3,5 entram nos intervalos válidos.
    assert row["amostras_sistema"] == 4
    assert "Sincronização" in row["avisos"]
    assert row["correcao_monitor_s"] == 2


def test_queda_de_usuarios_nao_une_segmentos(run):
    path = run / "medicao_stats_history.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    rows[2]["User Count"] = 0
    write_csv(path, rows)
    row = analysis.consolidar(run, options())
    assert row["req_janela"] is None
    assert "Queda de usuários" in row["avisos"]


def test_reset_contadores_rejeitado(run):
    path = run / "medicao_stats_history.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    rows[3]["Total Request Count"] = 1
    write_csv(path, rows)
    with pytest.raises(analysis.DadosInvalidos, match="Contador diminuiu"):
        analysis.consolidar(run, options())


def test_saida_e_originais_preservados(run, tmp_path):
    baseline = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
    args = [str(run), "--saida", str(tmp_path / "analise"),
            "--inicio-utc", "2026-10-08T16:00:01Z", "--fim-utc", "2026-10-08T16:00:09Z"]
    assert analysis.main(args) == 0
    with (tmp_path / "analise/consolidado.csv").open(encoding="utf-8", newline="") as source:
        assert len(list(csv.DictReader(source))) == 1
    with pytest.raises(SystemExit) as error:
        analysis.main(args)
    assert error.value.code == 1
    assert all(path.read_bytes() == data for path, data in baseline.items())


def test_duplicacao_e_saida_dentro_originais(run, tmp_path):
    with pytest.raises(SystemExit):
        analysis.main([str(run), str(run), "--saida", str(tmp_path / "analise")])
    assert not (tmp_path / "analise").exists()
    with pytest.raises(SystemExit):
        analysis.main([str(run), "--saida", str(run / "analise")])
    assert not (run / "analise").exists()


def test_intervalo_cpu_cruza_fronteira_excluido():
    rows = [{"utc": "2026-10-08T16:00:03Z", "intervalo_real_s": 3}]
    assert not analysis.filtrar(rows, analysis.instante("2026-10-08T16:00:02Z"),
                               analysis.instante("2026-10-08T16:00:08Z"), 0, "intervalo_real_s", [])


def test_metadados_linux_vazios_rejeitados(run):
    (run / "monitoramento_linux/metadados.json").write_text("{}", encoding="utf-8")
    with pytest.raises(analysis.DadosInvalidos, match="outro cenário"):
        analysis.consolidar(run, options())


def test_janela_prefere_marcos_diretos_sem_console(run):
    path = run / "parametros.json"
    data = json.loads(path.read_text())
    data["fases"][1]["instrumentacao"] = {
        "usuarios_prontos_utc": "2026-10-08T16:00:01Z",
        "encerramento_inicio_utc": "2026-10-08T16:00:09Z"}
    path.write_text(json.dumps(data), encoding="utf-8")
    row = analysis.consolidar(run, options(inicio_utc=None, fim_utc=None))
    assert row["req_janela"] == 6
    assert row["origem_janela"] == "marcos UTC diretos do Locust"


def alterar_metadata(run, **updates):
    path = run / "parametros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(updates)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.mark.parametrize("offset,shift,n", [(-2, 2, 4), (2, -2, 3)])
def test_offset_automatico_convencao_sinais(run, offset, shift, n):
    alterar_metadata(run, verificacao_relogio={"url": "http://localhost:8001", "coletado_utc": "2026-10-08T15:59:59Z",
                     "menor_incerteza": {"offset_estimado_s": offset, "incerteza_meia_faixa_s": .01}})
    row = analysis.consolidar(run, options(correcao_monitor_s=None, relogios_sincronizados=False))
    assert row["correcao_monitor_s"] == shift
    assert row["incerteza_offset_s"] == .01
    assert row["idade_sondagem_inicio_medicao_s"] == 1
    assert row["amostras_sistema"] == n
    assert "assume offset constante" in row["avisos"]
    # Override explícito 0 preserva a possibilidade de análise sem correção.
    assert analysis.consolidar(run, options())["correcao_monitor_s"] == 0


@pytest.mark.parametrize("probe", [{}, {"offset_estimado_s": "nan", "incerteza_meia_faixa_s": 1},
                                    {"offset_estimado_s": -2, "incerteza_meia_faixa_s": -1}])
def test_sondagem_ausente_invalida(run, probe):
    alterar_metadata(run, verificacao_relogio={"url": "http://localhost:8001", "menor_incerteza": probe})
    row = analysis.consolidar(run, options(correcao_monitor_s=None))
    assert row["correcao_monitor_s"] == 0
    assert "alinhamento temporal não comprovado" in row["avisos"]


def adicionar_latencias(run, complete=True):
    data = json.loads((run / "parametros.json").read_text(encoding="utf-8"))
    data["fases"][1]["instrumentacao"] = {
        "usuarios_prontos_utc": "2026-10-08T16:00:01Z", "encerramento_inicio_utc": "2026-10-08T16:00:09Z",
        "latencias": {"completo": complete, "registros": 20}}
    alterar_metadata(run, fases=data["fases"])
    # 20 eventos entre 2 e 8; p95 posto 19, média 10.5. Nenhum aquecimento.
    rows = [{"concluida_utc": f"2026-10-08T16:00:05.{i:06d}Z", "latencia_ms": i,
             "falha": int(i == 20)} for i in range(1, 21)]
    write_csv(run / "medicao_latencias.csv", rows)
    return rows


def test_latencias_exatas_media_p95_e_snapshots_separados(run):
    adicionar_latencias(run)
    row = analysis.consolidar(run, options(latencias_completas=False))
    assert row["latencia_media_calculada_janela_ms"] == 10.5
    assert row["p95_janela_ms"] == 19
    assert row["p95_snapshot_ms"] == 90
    assert row["req_hist_janela"] == 6
    assert row["req_janela"] == 20
    assert row["falhas_janela"] == 1
    assert row["vazao_calculada_janela_rps"] == 2.5  # eventos / 8 s, não usuários.
    assert row["duracao_janela_s"] == 8
    assert "Média de latência da janela não calculada" not in row["avisos"]


def test_recorte_eventos_e_percentil_pequeno(run):
    rows = adicionar_latencias(run)
    rows[0]["concluida_utc"] = "2026-10-08T16:00:01Z"  # borda inicial excluída
    rows[-1]["concluida_utc"] = "2026-10-08T16:00:09Z"  # fim de outro recorte
    write_csv(run / "medicao_latencias.csv", rows)
    row = analysis.consolidar(run, options(fim_utc="2026-10-08T16:00:08Z"))
    assert row["latencias_janela_n"] == 18
    assert row["latencia_media_calculada_janela_ms"] == 10.5
    assert row["p95_janela_ms"] == 19  # ceil(.95*18)=18


def test_recorte_nao_inclui_rampa(run):
    adicionar_latencias(run)
    with pytest.raises(analysis.DadosInvalidos, match="rampa"):
        analysis.consolidar(run, options(inicio_utc="2026-10-08T16:00:00Z"))


def test_sem_eventos_na_janela_nao_inventa_latencia(run):
    rows = adicionar_latencias(run)
    for row in rows:
        row["concluida_utc"] = "2026-10-08T16:00:09Z"
    write_csv(run / "medicao_latencias.csv", rows)
    row = analysis.consolidar(run, options(fim_utc="2026-10-08T16:00:08Z"))
    assert row["req_janela"] == 0
    assert row["p95_janela_ms"] is None
    assert row["latencia_media_calculada_janela_ms"] is None


def test_sondagem_outro_alvo_nao_aplicada(run):
    alterar_metadata(run, verificacao_relogio={"url": "http://outra-vm:8001", "menor_incerteza": {
        "offset_estimado_s": -2, "incerteza_meia_faixa_s": .01}})
    row = analysis.consolidar(run, options(correcao_monitor_s=None))
    assert row["correcao_monitor_s"] == 0


@pytest.mark.parametrize("mode", ["incompleto", "latencia_ausente", "timestamp_invalido", "contagem"])
def test_dados_individuais_incompletos_nao_inventam_percentil(run, mode):
    rows = adicionar_latencias(run, complete=mode != "incompleto")
    if mode == "latencia_ausente":
        rows[0]["latencia_ms"] = ""
    elif mode == "timestamp_invalido":
        rows[0]["concluida_utc"] = "2026-10-08T16:00:05"  # sem UTC
    elif mode == "contagem":
        rows.pop()
    write_csv(run / "medicao_latencias.csv", rows)
    row = analysis.consolidar(run, options(latencias_completas=False))
    assert row["p95_janela_ms"] is None
    assert row["latencia_media_calculada_janela_ms"] is None


def test_deltas_cpu_normalizacao_e_incompatibilidade_global(tmp_path):
    path = tmp_path / "cpu_bruto.jsonl"
    baseline = {"tipo": "baseline", "sistema": {"proc_stat_cpu_linhas": ["cpu 0 0 0 0 0 0 0 0 0 0"],
                "utc": "2026-10-08T16:00:02Z", "monotonic_after_s": 2, "clk_tck": 100}}
    record = {"amostra": 1, "sistema": {"proc_stat_cpu_linhas": ["cpu 20 0 0 30 0 0 0 0 0 0"],
              "utc": "2026-10-08T16:00:03Z", "monotonic_after_s": 3, "clk_tck": 100},
              "processos": [{"pid": 42, "criado_epoch_s": 1, "anterior": [1, 2],
                             "monotonic_s": 3, "cpu_times_s": {"user": 1.8, "system": 0, "children_user": 999}}]}
    path.write_text(json.dumps(baseline) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
    rows = [{"amostra": "1", "pid": "42", "criado_epoch_s": "1", "cpu_uma_cpu_pct": 80,
             "cpu_capacidade_vm_pct": 40, "cpu_intervalo_real_s": 1}]
    output, warnings = {}, []
    analysis.verificar_cpu_bruto(path, rows, analysis.instante("2026-10-08T16:00:02Z"),
                                 analysis.instante("2026-10-08T16:00:04Z"), 0, 2, output, warnings)
    assert output["cpu_bruto_processos_n"] == 1
    assert output["cpu_bruto_processos_erro_max_pp"] < 1e-12
    assert output["cpu_bruto_processos_tempo_s"] == pytest.approx(.8)
    assert output["cpu_bruto_sistema_total_s"] == .5
    assert any("fontes não reconciliadas" in warning for warning in warnings)
    assert any("menor que tempo da árvore" in warning for warning in warnings)
    rows[0]["cpu_uma_cpu_pct"] = 10
    warnings.clear()
    analysis.verificar_cpu_bruto(path, rows, analysis.instante("2026-10-08T16:00:02Z"),
                                 analysis.instante("2026-10-08T16:00:04Z"), 0, 2, output, warnings)
    assert any("inconsistente com os deltas" in warning for warning in warnings)
