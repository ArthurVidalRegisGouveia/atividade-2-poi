"""Quatro agregados sintéticos isolados; nenhuma carga ou fonte experimental real."""

import csv
import pytest

from scripts.analise import comparar_cenarios as comparison


def write(path,rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


@pytest.fixture
def fontes(tmp_path,monkeypatch):
    monkeypatch.setattr(comparison,"ROOT",tmp_path)
    sources = {}
    for i,c in enumerate(comparison.SCENARIOS):
        path = tmp_path/"experimentos/resultados/analise_final"/c/"agregados.csv"
        path.parent.mkdir(parents=True)
        rows = []
        for app,users in comparison.DEMANDAS.items():
            for u in users:
                for metric,(field,_,unit) in comparison.METRICAS.items():
                    if metric in comparison.DISCO and app != "io": continue
                    stats = comparison.estatistica([1+i,2+i,3+i])
                    if metric == "falhas": stats = comparison.estatistica([0,0,0])
                    if metric in ("uss_arvore_mib","pss_arvore_mib") and app == "cpu": stats = comparison.estatistica([None,None,None])
                    rows.append(dict(cenario=c,aplicacao=app,usuarios=u,repeticoes=3,metrica=metric,
                                     unidade=unit,campo_origem=field,dispositivo="sda" if metric in comparison.DISCO else "",**stats))
        write(path,rows); sources[c]=path
    return sources


def test_leitura_selecao_unidades_ausencias_e_fontes(fontes):
    original = {p:p.read_bytes() for p in fontes.values()}
    rows,provenance = comparison.carregar(fontes)
    assert len(rows)==464 and len(provenance)==4
    assert all(p.read_bytes()==data for p,data in original.items())
    assert all(r['media'] is None for r in rows if r['aplicacao']=='cpu' and r['metrica']=='uss_arvore_mib')
    assert {r['dispositivo'] for r in rows if r['metrica'] in comparison.DISCO}=={'sda'}


@pytest.mark.parametrize("mode",["cenario","repeticoes","n","ausentes","unidade","origem","duplicada","faltante",
                                 "nan","negativo","dp","extremos","ausencia_preenchida","dispositivo","sem_dispositivo","coluna"])
def test_entradas_inconsistentes_rejeitadas(fontes,mode):
    path=fontes['C2']
    with path.open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
    row=rows[0]
    if mode=='cenario': row['cenario']='C1'
    elif mode=='repeticoes': row['repeticoes']=2
    elif mode=='n': row['n_validos']=2
    elif mode=='ausentes': row['ausentes']=1
    elif mode=='unidade': row['unidade']='bytes'
    elif mode=='origem': row['campo_origem']='vazao_snapshot_rps'
    elif mode=='duplicada': rows.append(dict(row))
    elif mode=='faltante': rows.pop()
    elif mode=='nan': row['media']='nan'
    elif mode=='negativo': row['desvio_padrao_amostral']=-1
    elif mode=='dp': row['desvio_padrao_amostral']=20
    elif mode=='extremos': row['maximo']=2
    elif mode=='ausencia_preenchida': next(r for r in rows if r['metrica']=='uss_arvore_mib')['media']=0
    elif mode=='dispositivo':
        for r in rows:
            if r['metrica'] in comparison.DISCO: r['dispositivo']='sda5'
    elif mode=='sem_dispositivo': next(r for r in rows if r['metrica'] in comparison.DISCO)['dispositivo']=''
    else:
        for r in rows: r.pop('unidade')
    write(path,rows)
    with pytest.raises(ValueError): comparison.carregar(fontes)


def test_quatro_fontes_exigidas(fontes):
    with pytest.raises(ValueError): comparison.carregar({k:v for k,v in fontes.items() if k!='C3'})


@pytest.mark.parametrize("base,target,absolute,percent",[(10,15,5,50),(10,5,-5,-50),(0,0,0,None),(0,2,2,None),(None,2,None,None),(2,None,None,None)])
def test_diferencas_denominador_zero_e_ausencias(base,target,absolute,percent):
    result=comparison.diferenca(base,target)
    assert result['diferenca_absoluta']==absolute and result['diferenca_percentual']==percent
    if percent is None: assert result['motivo']


def test_pares_sem_causalidade_e_sem_somar_disco(fontes):
    rows,_=comparison.carregar(fontes)
    tables,differences=comparison.comparar(rows)
    assert len(tables)==116 and len(differences)==464
    cpu=next(r for r in differences if (r['cenario_base'],r['cenario_comparado'],r['aplicacao'],r['usuarios'],r['metrica'])==('C1','C3','cpu',2,'vazao_rps'))
    assert cpu['diferenca_absoluta']==2 and cpu['diferenca_percentual']==100
    assert cpu['alteracao']=='mudança conjunta de vCPUs e workers'
    failures=[r for r in differences if r['metrica']=='falhas']
    assert all(r['diferenca_absoluta']==0 and r['diferenca_percentual'] is None for r in failures)
    disk=next(r for r in tables if r['metrica']=='escrita_mib_s')
    assert disk['C1_media']==2 and disk['dispositivo']=='sda'


def test_opcional_parcial_sem_imputacao(fontes):
    path=fontes['C1']
    with path.open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
    metric=next(r for r in rows if r['aplicacao']=='memoria' and r['metrica']=='uss_arvore_mib')
    metric.update(comparison.estatistica([1,3,None]))
    write(path,rows)
    loaded,_=comparison.carregar(fontes)
    actual=next(r for r in loaded if r['cenario']=='C1' and r['aplicacao']=='memoria' and r['metrica']=='uss_arvore_mib')
    assert actual['n_validos']==2 and actual['ausentes']==1 and actual['media']==2


def test_arquivos_graficos_relatorio_preservacao_e_sobrescrita(fontes,tmp_path):
    pytest.importorskip('matplotlib')
    original={p:p.read_bytes() for p in fontes.values()}
    output=tmp_path/'experimentos/resultados/analise_final/comparativo_C1_C4'
    assert comparison.main([])==0
    assert len(list(output.glob('*.png')))==16 and len(list(output.glob('*.svg')))==16
    report=(output/'relatorio.md').read_text(encoding='utf-8')
    for text in ('atualização do Ubuntu','recuperadas em novas execuções','não são intervalos de confiança','C1→C3'):
        assert text in report
    assert all(p.read_bytes()==data for p,data in original.items())
    original_output=(output/'comparativos.csv').read_bytes()
    with pytest.raises(SystemExit): comparison.main([])
    assert (output/'comparativos.csv').read_bytes()==original_output
    with pytest.raises(SystemExit): comparison.main(['--saida',str(fontes['C1'].parent/'comparacao')])
