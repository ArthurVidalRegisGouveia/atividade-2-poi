from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import runpy
from threading import BoundedSemaphore, Event, Lock

import pytest
from fastapi.testclient import TestClient

from apps.io_bound import main


@pytest.fixture
def diretorio_io(tmp_path, monkeypatch):
    diretorio = tmp_path / "io_isolado"
    monkeypatch.setattr(main, "DIRETORIO_TEMP", diretorio)
    return diretorio


@pytest.fixture
def client(diretorio_io):
    with TestClient(main.app) as cliente:
        yield cliente


def resposta_esperada(tamanho_mb, operacoes):
    bytes_por_sentido = tamanho_mb * 1024 * 1024 * operacoes
    return {
        "tipo": "I/O-bound", "tamanho_mb": tamanho_mb, "operacoes": operacoes,
        "bytes_escritos": bytes_por_sentido, "bytes_lidos": bytes_por_sentido,
        "bytes_processados": bytes_por_sentido * 2, "verificacao": "ok",
    }


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_criacao_controlada_do_diretorio(diretorio_io):
    assert not diretorio_io.exists()
    with TestClient(main.app):
        assert diretorio_io.is_dir()
        assert list(diretorio_io.iterdir()) == []


@pytest.mark.parametrize(("tamanho_mb", "operacoes"), [(1, 1), (1, 2), (2, 2)])
def test_resposta_e_limpeza(client, diretorio_io, tamanho_mb, operacoes):
    response = client.get("/arquivo", params={"tamanho_mb": tamanho_mb, "operacoes": operacoes})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == resposta_esperada(tamanho_mb, operacoes)
    for campo in ("tamanho_mb", "operacoes", "bytes_escritos", "bytes_lidos", "bytes_processados"):
        assert type(response.json()[campo]) is int
    assert list(diretorio_io.iterdir()) == []


def test_parametros_padrao(client, diretorio_io):
    response = client.get("/arquivo")
    assert response.status_code == 200
    assert response.json() == resposta_esperada(10, 1)
    assert list(diretorio_io.iterdir()) == []


@pytest.mark.parametrize(
    ("campo", "valor"),
    [(campo, valor) for campo in ("tamanho_mb", "operacoes")
     for valor in ("0", "-1", "abc", "1.5", "")]
    + [("tamanho_mb", "33"), ("operacoes", "6")],
)
def test_parametros_invalidos_sem_criar_arquivo(client, diretorio_io, monkeypatch, campo, valor):
    def criacao_proibida(**kwargs):
        pytest.fail("Entrada inválida não deve criar um arquivo.")

    monkeypatch.setattr(main, "NamedTemporaryFile", criacao_proibida)
    response = client.get("/arquivo", params={campo: valor})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/json"
    assert response.json()["detail"][0]["loc"] == ["query", campo]
    assert list(diretorio_io.iterdir()) == []


def test_arquivo_real_por_operacao_e_preservacao(client, diretorio_io, monkeypatch):
    arquivo_usuario = diretorio_io / "preservar.txt"
    arquivo_usuario.write_text("conteúdo do usuário", encoding="utf-8")
    caminhos = []
    processar_original = main.processar_arquivo

    def observar(arquivo, tamanho_bytes):
        caminho = Path(arquivo.name)
        assert caminho.is_file()
        assert caminho.parent == diretorio_io
        assert len(list(diretorio_io.glob("io_bound_*.tmp"))) == 1
        caminhos.append(caminho)
        resultado = processar_original(arquivo, tamanho_bytes)
        assert caminho.stat().st_size == tamanho_bytes
        return resultado

    monkeypatch.setattr(main, "processar_arquivo", observar)
    assert client.get("/arquivo", params={"tamanho_mb": 1, "operacoes": 2}).status_code == 200
    assert len(caminhos) == len(set(caminhos)) == 2
    assert all(not caminho.exists() for caminho in caminhos)
    assert arquivo_usuario.read_text(encoding="utf-8") == "conteúdo do usuário"


class ArquivoObservado:
    def __init__(self, arquivo):
        self.arquivo = arquivo
        self.escritas = []
        self.leituras = []

    def __getattr__(self, nome):
        return getattr(self.arquivo, nome)

    def write(self, dados):
        self.escritas.append(len(dados))
        return self.arquivo.write(dados)

    def read(self, tamanho):
        self.leituras.append(tamanho)
        return self.arquivo.read(tamanho)


@pytest.mark.parametrize("tamanho", [17, main.TAMANHO_BLOCO, main.TAMANHO_BLOCO + 17])
def test_blocos_e_integridade(tmp_path, tamanho):
    with (tmp_path / "blocos.bin").open("w+b") as arquivo:
        observado = ArquivoObservado(arquivo)
        assert main.processar_arquivo(observado, tamanho) == (tamanho, tamanho)
        assert max(observado.escritas) <= main.TAMANHO_BLOCO
        assert max(observado.leituras) <= main.TAMANHO_BLOCO
        assert sum(observado.escritas) == tamanho
        arquivo.seek(0)
        # Conteúdo pequeno neste teste; a aplicação sempre usa blocos.
        assert arquivo.read() == b"\xa5" * tamanho


@pytest.mark.parametrize("falha", ["conteudo", "truncado", "extra"])
def test_detecta_corrupcao_e_limpa(client, diretorio_io, monkeypatch, falha):
    processar_original = main.processar_arquivo
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))

    class ArquivoCorrompido(ArquivoObservado):
        def read(self, tamanho):
            dados = super().read(tamanho)
            if falha == "conteudo" and dados:
                return b"X" + dados[1:]
            if falha == "truncado" and dados:
                return dados[:-1]
            if falha == "extra" and tamanho == 1:
                return b"X"
            return dados

    def corromper(arquivo, tamanho_bytes):
        return processar_original(ArquivoCorrompido(arquivo), tamanho_bytes)

    monkeypatch.setattr(main, "processar_arquivo", corromper)
    response = client.get("/arquivo", params={"tamanho_mb": 1})
    assert response.status_code == 500
    assert response.json() == {"detail": "Falha na verificação do arquivo."}
    assert list(diretorio_io.iterdir()) == []
    monkeypatch.setattr(main, "processar_arquivo", processar_original)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 200


@pytest.mark.parametrize("falha", ["escrita", "leitura", "escrita_curta", "fsync"])
def test_falhas_de_io_limpeza_e_vaga(client, diretorio_io, monkeypatch, falha):
    processar_original = main.processar_arquivo
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))

    class ArquivoComFalha(ArquivoObservado):
        def write(self, dados):
            if falha in ("escrita", "escrita_curta"):
                self.arquivo.write(dados[:10])
                if falha == "escrita_curta":
                    return 10
                raise OSError("Falha simulada na escrita.")
            return super().write(dados)

        def read(self, tamanho):
            if falha == "leitura":
                raise OSError("Falha simulada na leitura.")
            return super().read(tamanho)

    def executar_com_falha(arquivo, tamanho_bytes):
        return processar_original(ArquivoComFalha(arquivo), tamanho_bytes)

    if falha == "fsync":
        monkeypatch.setattr(main, "FSYNC", True)

        def falhar_fsync(descritor):
            raise OSError("Falha simulada no fsync.")

        monkeypatch.setattr(main.os, "fsync", falhar_fsync)
    monkeypatch.setattr(main, "processar_arquivo", executar_com_falha)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 507
    assert list(diretorio_io.iterdir()) == []
    monkeypatch.setattr(main, "processar_arquivo", processar_original)
    monkeypatch.setattr(main, "FSYNC", False)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 200


def test_falha_na_criacao_devolve_vaga(client, diretorio_io, monkeypatch):
    criar_original = main.NamedTemporaryFile
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(1))

    def falhar(**kwargs):
        raise OSError("Falha simulada na criação.")

    monkeypatch.setattr(main, "NamedTemporaryFile", falhar)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 507
    assert list(diretorio_io.iterdir()) == []
    monkeypatch.setattr(main, "NamedTemporaryFile", criar_original)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 200


@pytest.mark.parametrize("habilitado", [False, True])
def test_fsync_configuravel_e_real(client, diretorio_io, monkeypatch, habilitado):
    fsync_original = main.os.fsync
    chamadas = []

    def sincronizar(descritor):
        chamadas.append(descritor)
        return fsync_original(descritor)

    monkeypatch.setattr(main, "FSYNC", habilitado)
    monkeypatch.setattr(main.os, "fsync", sincronizar)
    assert client.get("/arquivo", params={"tamanho_mb": 1}).status_code == 200
    assert len(chamadas) == int(habilitado)
    assert list(diretorio_io.iterdir()) == []


def test_concorrencia_nomes_exclusivos_e_limpeza(client, diretorio_io, monkeypatch):
    processar_original = main.processar_arquivo
    monkeypatch.setattr(main, "vagas", BoundedSemaphore(2))
    caminhos = []
    lock = Lock()
    dois_arquivos = Event()
    liberar = Event()

    def observar(arquivo, tamanho_bytes):
        resultado = processar_original(arquivo, tamanho_bytes)
        with lock:
            caminhos.append(Path(arquivo.name))
            if len(caminhos) == 2:
                dois_arquivos.set()
        if not liberar.wait(timeout=10):
            raise RuntimeError("O teste não liberou os arquivos.")
        return resultado

    monkeypatch.setattr(main, "processar_arquivo", observar)
    with ThreadPoolExecutor(max_workers=3) as executor:
        pedidos = [executor.submit(client.get, "/arquivo", params={"tamanho_mb": 1}) for _ in range(2)]
        try:
            assert dois_arquivos.wait(timeout=5)
            assert len(set(caminhos)) == 2
            assert all(caminho.is_file() for caminho in caminhos)
            assert len(list(diretorio_io.iterdir())) == 2
            assert executor.submit(client.get, "/health").result(timeout=5).status_code == 200
            assert executor.submit(client.get, "/arquivo", params={"tamanho_mb": 1}).result(timeout=5).status_code == 503
        finally:
            liberar.set()
        assert all(pedido.result(timeout=5).status_code == 200 for pedido in pedidos)
    assert list(diretorio_io.iterdir()) == []


def carregar_configuracao():
    return runpy.run_path(str(Path(__file__).parents[1] / "apps/io_bound/main.py"))


def test_limites_e_diretorio_configuraveis(tmp_path, monkeypatch):
    pasta = tmp_path / "configurado"
    monkeypatch.setenv("IO_DIRETORIO_TEMP", str(pasta))
    monkeypatch.setenv("IO_TAMANHO_MAX_MB", "2")
    monkeypatch.setenv("IO_OPERACOES_MAX", "2")
    monkeypatch.setenv("IO_MAX_SIMULTANEAS", "1")
    monkeypatch.setenv("IO_FSYNC", "1")
    modulo = carregar_configuracao()
    assert modulo["DIRETORIO_TEMP"] == pasta
    assert modulo["FSYNC"] is True
    assert not pasta.exists()
    with TestClient(modulo["app"]) as client:
        assert client.get("/arquivo", params={"tamanho_mb": 3}).status_code == 422
        assert client.get("/arquivo", params={"operacoes": 3}).status_code == 422
        assert client.get("/arquivo").json() == resposta_esperada(2, 1)
        assert client.get("/arquivo", params={"tamanho_mb": 2, "operacoes": 2}).status_code == 200
    assert list(pasta.iterdir()) == []


def test_caminho_relativo_e_rejeicao_de_raiz(monkeypatch):
    monkeypatch.setenv("IO_DIRETORIO_TEMP", ".temp/io_teste_config")
    modulo = carregar_configuracao()
    assert modulo["DIRETORIO_TEMP"] == Path(__file__).parents[1] / ".temp/io_teste_config"
    monkeypatch.setenv("IO_DIRETORIO_TEMP", Path(__file__).anchor)
    with pytest.raises(ValueError):
        carregar_configuracao()


@pytest.mark.parametrize(
    ("variavel", "valor"),
    [
        ("IO_TAMANHO_MAX_MB", "0"), ("IO_TAMANHO_MAX_MB", "-1"),
        ("IO_TAMANHO_MAX_MB", "abc"), ("IO_TAMANHO_MAX_MB", "65"),
        ("IO_OPERACOES_MAX", "0"), ("IO_OPERACOES_MAX", "6"),
        ("IO_MAX_SIMULTANEAS", "0"), ("IO_MAX_SIMULTANEAS", "5"),
        ("IO_FSYNC", "true"),
    ],
)
def test_configuracao_invalida(monkeypatch, variavel, valor):
    monkeypatch.setenv(variavel, valor)
    with pytest.raises(ValueError):
        carregar_configuracao()
