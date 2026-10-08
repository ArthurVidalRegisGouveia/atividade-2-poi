"""Registro bufferizado testado sem carregar Locust nem enviar HTTP."""

import csv

import pytest

from scripts.carga.latencias import RegistroLatencias


def test_registro_exclui_rampa_drenagem_e_limita_volume(tmp_path):
    path = tmp_path / "latencias.csv"
    recorder = RegistroLatencias(path, 2)
    recorder.registrar(0, 99, False)
    recorder.ativo = True
    recorder.registrar(1, 10.5, False, "1424")
    recorder.registrar(2, 20, True, "1425")
    recorder.registrar(3, 30, False)
    recorder.fechar()
    recorder.registrar(4, 40, False)
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 2
    assert rows[0]["concluida_utc"] == "1970-01-01T00:00:01+00:00"
    assert rows[0]["latencia_ms"] == "10.5"
    assert rows[1]["falha"] == "1"
    assert recorder.metadados()["descartados"] == 1
    assert not recorder.metadados()["completo"]
    with pytest.raises(FileExistsError):
        RegistroLatencias(path)


@pytest.mark.parametrize("value", [None, "", float("nan"), float("inf"), -1])
def test_latencia_ausente_invalida_nao_completa(tmp_path, value):
    recorder = RegistroLatencias(tmp_path / "latencias.csv")
    recorder.ativo = True
    recorder.registrar(1, value, True)
    recorder.fechar()
    assert recorder.metadados()["invalidos"] == 1
    assert not recorder.metadados()["completo"]


@pytest.mark.parametrize("value", [0, -1, 1000001])
def test_limites_de_armazenamento(tmp_path, value):
    with pytest.raises(ValueError):
        RegistroLatencias(tmp_path / "latencias.csv", value)
    assert not list(tmp_path.iterdir())


def test_erro_escrita_marca_incompleto(tmp_path, monkeypatch):
    from types import SimpleNamespace
    recorder = RegistroLatencias(tmp_path / "latencias.csv")
    recorder.ativo = True

    def fail(row):
        raise OSError("Erro simulado")

    monkeypatch.setattr(recorder, "writer", SimpleNamespace(writerow=fail))
    recorder.registrar(1, 10, False)
    recorder.fechar()
    assert recorder.metadados()["erros_escrita"] == 1
    assert not recorder.metadados()["completo"]
