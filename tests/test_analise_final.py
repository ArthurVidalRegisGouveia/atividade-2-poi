"""Campanha sintética isolada; não lê nem altera resultados experimentais reais."""

import csv
import json

import pytest

from scripts.analise import analisar_definitivos as final


def csv_file(path, row):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def construir_campanha(tmp_path, scenario="C4", base=2000):
    directory = tmp_path / f"experimentos/resultados/orquestracao/definitivos_{scenario}_01"
    directory.mkdir(parents=True)
    entries = []
    for app, users in final.DEMANDAS.items():
        for u in users:
            for logical in (1, 2, 3):
                recovered = (app, u, logical) == (("cpu", 10, 2) if scenario == "C3" else ("io", 2, 2))
                physical = base + logical + (10 if recovered else 0)
                job = dict(cenario=scenario, aplicacao=app, usuarios=u, repeticao=physical,
                           repeticao_logica=logical, tentativa=2 if recovered else 1)
                folder = directory / f"{app}_{u}_{physical}"
                analysis = folder / "analise"
                analysis.mkdir(parents=True)
                row = dict(cenario=scenario, aplicacao=app, usuarios=u, repeticao=physical,
                           inicio_janela_utc="2026-10-08T12:00:00Z", fim_janela_utc="2026-10-08T12:01:00Z",
                           req_janela=60, amostras_sistema=59, avisos="Sincronização provisória | CPU global divergente")
                for name, (field, divisor, _) in final.METRICAS.items():
                    if name not in final.DISCO: row[field] = logical * divisor
                row["falhas_janela"] = 0
                row["uss_soma_bytes_media"] = ""
                row["pss_soma_bytes_media"] = ""
                row["vazao_snapshot_rps"] = 999
                row["discos_janela"] = json.dumps({
                    "sda": {"escrita_bytes_s_media": 10 * 1024**2, "escrita_bytes_delta_soma": 600 * 1024**2,
                            "escritas_delta_soma": 123, "ocupado_ms_delta_soma": 100},
                    "sda5": {"escrita_bytes_s_media": 10 * 1024**2, "escrita_bytes_delta_soma": 600 * 1024**2}})
                csv_file(analysis / "consolidado.csv", row)
                manifest = folder / "manifesto.json"
                manifest.write_text(json.dumps(dict(estado="concluída", job=job, analise=str(analysis))), encoding="utf-8")
                entries.append(dict(estado="concluída", job=job, manifesto=str(manifest)))
    failed = dict(entries[-1])
    app, users = ("cpu", 10) if scenario == "C3" else ("io", 2)
    failed["job"] = dict(cenario=scenario, aplicacao=app, usuarios=users, repeticao=base+2, repeticao_logica=2, tentativa=1)
    failed["estado"] = "falha"
    failed["manifesto"] = "não será lido"
    entries.append(failed)
    exploratory = dict(failed, estado="concluída", job={**failed["job"], "repeticao": 1001})
    entries.append(exploratory)
    index = directory / "indice.json"
    index.write_text(json.dumps(entries), encoding="utf-8")
    return index


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(final, "ROOT", tmp_path)
    return construir_campanha(tmp_path)


@pytest.mark.parametrize("scenario,base", [("C3",3000), ("C4",2000), ("C1",1000), ("C2",5000)])
def test_cenarios_base_inferida_recuperacao_e_textos(tmp_path, monkeypatch, scenario, base):
    # Bases de C1/C2 são dados sintéticos legais, não atribuições às campanhas reais.
    monkeypatch.setattr(final, "ROOT", tmp_path)
    index = construir_campanha(tmp_path, scenario, base)
    rows, excluded, _ = final.selecionar(index)
    assert len(rows) == 27 and len(excluded) == 2
    assert {r["base_repeticao"] for r in rows} == {base}
    app, users = ("cpu",10) if scenario == "C3" else ("io",2)
    selected = [r for r in rows if r["aplicacao"] == app and int(r["usuarios"]) == users]
    assert [int(r["repeticao"]) for r in selected] == [base+1,base+12,base+3]
    assert any(r["repeticao"] == base+2 and r["estado"] == "falha" for r in excluded)
    aggregated = final.agregar(rows)
    report = final.relatorio(rows, aggregated, excluded)
    assert report.startswith(f"# Análise definitiva — {scenario}")
    assert "duas vCPUs" not in report
    if scenario != "C4": assert "C4" not in report


@pytest.mark.parametrize("state", ["concluída", "falha"])
def test_indice_cenarios_misturados_rejeitado(campaign, state):
    entries = final.ler_json(campaign)
    entries[-1]["job"]["cenario"] = "C3"
    entries[-1]["estado"] = state
    campaign.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="cenários misturados"):
        final.selecionar(campaign)


def test_agregacao_cenarios_misturados_rejeitada(campaign):
    rows, _, _ = final.selecionar(campaign)
    rows[-1]["cenario"] = "C3"
    with pytest.raises(ValueError, match="cenários misturados"): final.agregar(rows)


def test_c3_repeticao_ausente_rejeitada(tmp_path, monkeypatch):
    monkeypatch.setattr(final, "ROOT", tmp_path)
    index = construir_campanha(tmp_path, "C3", 3000)
    entries = final.ler_json(index)
    entries = [e for e in entries if e["job"]["repeticao"] != 3012]
    index.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="três repetições válidas cpu/10"):
        final.selecionar(index)


def test_bases_completas_ambiguas_rejeitadas(campaign):
    entries = final.ler_json(campaign)
    copies = []
    for entry in entries[:27]:
        copies.append({**entry, "job": {**entry["job"], "repeticao": entry["job"]["repeticao"] + 1000}})
    campaign.write_text(json.dumps(entries + copies), encoding="utf-8")
    with pytest.raises(ValueError, match="Base da campanha ausente ou ambígua"):
        final.selecionar(campaign)


def test_c3_saida_padrao_e_titulos_svg(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.setattr(final, "ROOT", tmp_path)
    index = construir_campanha(tmp_path, "C3", 3000)
    output = tmp_path / "experimentos/resultados/analise_final/C3"
    assert final.main(["--indice",str(index)]) == 0
    assert (output / "relatorio.md").read_text(encoding="utf-8").startswith("# Análise definitiva — C3")
    assert "C3 · cpu" in (output / "cpu.svg").read_text(encoding="utf-8")
    audit = final.ler_json(output / "selecao.json")
    assert audit["cenario"] == "C3" and audit["base_repeticao"] == 3000


def test_selecao_substituta_sem_exploratorios_e_avisos(campaign):
    before = campaign.read_bytes()
    rows, excluded, sources = final.selecionar(campaign)
    assert len(rows) == 27 and len(excluded) == 2
    io = [r for r in rows if r["aplicacao"] == "io" and r["usuarios"] == "2"]
    assert [r["repeticao"] for r in io] == ["2001", "2012", "2003"]
    assert [r["repeticao_logica"] for r in io] == [1, 2, 3]
    assert rows[0]["vazao_rps"] == 1 and rows[0]["vazao_snapshot_rps"] == "999"
    assert "CPU global divergente" in rows[0]["avisos"]
    assert len(sources) == 55 and campaign.read_bytes() == before


@pytest.mark.parametrize("mode", ["ausente", "planejada", "falha", "duplicada", "manifesto", "identidade", "sem_carga", "campo_essencial"])
def test_repeticoes_invalidas_rejeitadas(campaign, mode):
    entries = final.ler_json(campaign)
    first = entries[0]
    manifest = final.ler_json(final.Path(first["manifesto"]))
    source = final.Path(manifest["analise"]) / "consolidado.csv"
    if mode == "ausente": entries.pop(0)
    elif mode in ("planejada", "falha"): first["estado"] = mode
    elif mode == "duplicada": entries.append(first)
    elif mode == "manifesto":
        manifest["estado"] = "falha"
        final.Path(first["manifesto"]).write_text(json.dumps(manifest), encoding="utf-8")
    else:
        with source.open(encoding="utf-8") as f: row = next(csv.DictReader(f))
        if mode == "identidade": row["repeticao"] = 9999
        elif mode == "sem_carga": row["req_janela"] = 0
        else: row["p95_janela_ms"] = ""
        csv_file(source, row)
    campaign.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError): final.selecionar(campaign)


def test_estatistica_amostral_e_ausentes():
    assert final.estatistica([1, 2, 3]) == dict(n_validos=3, ausentes=0, media=2,
                                             desvio_padrao_amostral=1, minimo=1, maximo=3)
    assert final.estatistica([None, "", "nan"])["media"] is None
    assert final.estatistica([7, None, "inf"])["desvio_padrao_amostral"] is None
    result = final.estatistica([1, None, 3])
    assert result["n_validos"] == 2 and result["ausentes"] == 1 and result["media"] == 2


def test_agregacao_e_disco_sem_duplicacao(campaign):
    rows, _, _ = final.selecionar(campaign)
    result = final.agregar(rows)
    metric = next(r for r in result if r["aplicacao"] == "cpu" and r["usuarios"] == 1 and r["metrica"] == "vazao_rps")
    assert metric["media"] == 2 and metric["desvio_padrao_amostral"] == 1
    assert all(r["escrita_mib_s"] == 10 for r in rows if r["aplicacao"] == "io")
    uss = [r for r in result if r["metrica"] == "uss_arvore_mib"]
    assert all(r["n_validos"] == 0 and r["media"] is None for r in uss)
    with pytest.raises(ValueError): final.agregar(rows + [rows[0]])


def test_disco_ausente_nao_imputado(campaign):
    rows, _, _ = final.selecionar(campaign, dispositivo="inexistente")
    io = [r for r in rows if r["aplicacao"] == "io"]
    assert all(r["escrita_mib_s"] is None and "Métrica ausente: escrita_mib_s" in r["avisos"] for r in io)


def test_parametros_distintos_nao_agregados(campaign):
    rows, _, _ = final.selecionar(campaign)
    rows[0]["conexoes"] = "reutilizar"
    with pytest.raises(ValueError, match="Parâmetros divergentes"): final.agregar(rows)


def test_saida_completa_e_recusa_sobrescrita(campaign, tmp_path):
    pytest.importorskip("matplotlib")
    original = {p: p.read_bytes() for p in campaign.parent.rglob("*") if p.is_file()}
    output = tmp_path / "experimentos/resultados/analise_final/C4"
    args = ["--indice", str(campaign), "--saida", str(output)]
    assert final.main(args) == 0
    assert len(list(output.glob("*.png"))) == 5
    assert len(list(output.glob("*.svg"))) == 5
    report = (output / "relatorio.md").read_text(encoding="utf-8")
    assert "hipóteses compatíveis" in report and "não comprovam" in report
    assert all(p.read_bytes() == b for p, b in original.items())
    before = (output / "individuais.csv").read_bytes()
    with pytest.raises(SystemExit): final.main(args)
    assert (output / "individuais.csv").read_bytes() == before
