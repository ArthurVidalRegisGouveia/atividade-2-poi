from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.monitoramento import verificar_relogios as clock


def test_offset_com_limites_de_rede():
    t1 = datetime(2026, 10, 8, tzinfo=timezone.utc)
    # Servidor atrasado 3 s; ida 0,1 s, processamento 0,02 s, volta 0,1 s.
    result = clock.calcular(t1, t1 + timedelta(seconds=-2.9),
                            t1 + timedelta(seconds=-2.88), t1 + timedelta(seconds=.22), .22)
    assert result["offset_estimado_s"] == pytest.approx(-3)
    assert result["offset_servidor_menos_cliente_min_s"] == pytest.approx(-3.1)
    assert result["offset_servidor_menos_cliente_max_s"] == pytest.approx(-2.9)
    assert result["incerteza_meia_faixa_s"] == pytest.approx(.1)


def test_salto_relogio_rejeitado():
    t = datetime(2026, 10, 8, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        clock.calcular(t, t, t, t + timedelta(seconds=10), .1)


def test_saida_e_ausencia_cabecalho(tmp_path, monkeypatch):
    def missing(url): raise KeyError("X-Server-Received-UTC")
    monkeypatch.setattr(clock, "sondar", missing)
    output = tmp_path / "relogios.json"
    assert clock.main(["--amostras", "1", "--saida", str(output)]) == 1
    data = json.loads(output.read_text())
    assert data["menor_incerteza"] is None
    assert data["amostras"][0]["erro"] == "KeyError"
    with pytest.raises(SystemExit):
        clock.main(["--saida", str(output)])
    assert output.read_text() == json.dumps(data, indent=2) + "\n"
