# Atividade 2 — Demanda, Provisionamento e Desempenho

Projeto acadêmico para estudar como o provisionamento de CPU e memória de uma máquina virtual influencia o desempenho de aplicações HTTP com perfis **CPU-bound**, **Memory-bound** e **I/O-bound**.

Foram executados **108 testes válidos** em quatro cenários de recursos, com geração de carga pelo **Locust no Windows (host)** e execução das APIs em uma **VM Ubuntu Server 22.04 no Oracle VirtualBox**. O projeto inclui monitoramento da VM, orquestração, consolidação estatística e gráficos comparativos.

## Arquitetura e tecnologias

```text
Windows (host)                             Ubuntu Server (VirtualBox)
Locust + orquestrador  ── HTTP / NAT ──►  FastAPI + Uvicorn (portas 8001–8003)
                     ◄── SSH / SCP ────   psutil + monitoramento Linux
```

- **Aplicações:** Python, FastAPI e Uvicorn.
- **Geração de carga:** Locust, executado externamente à VM.
- **Monitoramento:** psutil, informações dos processos e contadores de disco Linux.
- **Automação e análise:** scripts Python, pytest e Matplotlib.
- **Comunicação:** encaminhamento de portas NAT do VirtualBox e SSH/SCP.

## Aplicações

| Perfil | Endpoint | Configuração dos testes definitivos | Porta |
| --- | --- | --- | ---: |
| CPU-bound | `GET /primos?limite=250000` | Contagem de números primos até 250.000 | 8001 |
| Memory-bound | `GET /memoria?tamanho_mb=50` | 50 MiB por requisição; retenção de 1 s | 8002 |
| I/O-bound | `GET /arquivo?tamanho_mb=10&operacoes=1` | Arquivo de 10 MiB; 1 operação; `IO_FSYNC=1` | 8003 |

As três APIs oferecem `GET /health`. As configurações de retenção e `fsync` são **variáveis de ambiente do servidor**, não parâmetros HTTP.

## Cenários e metodologia

| Cenário | vCPUs | RAM | Workers Uvicorn |
| --- | ---: | ---: | ---: |
| C1 | 1 | 1 GiB | 1 |
| C2 | 1 | 2 GiB | 1 |
| C3 | 2 | 1 GiB | 2 |
| C4 | 2 | 2 GiB | 2 |

- **CPU-bound:** 1, 2, 5 e 10 usuários concorrentes.
- **Memory-bound:** 1, 2 e 3 usuários concorrentes.
- **I/O-bound:** 1 e 2 usuários concorrentes.
- **Por combinação:** 30 s de aquecimento, 60 s de medição configurada e três repetições válidas.
- **Política da carga:** espera de 0 s entre requisições e fechamento das conexões HTTP.
- **Monitoramento:** amostras aproximadamente a cada 1 s, abrangendo CPU, memória e, no perfil I/O, atividade de disco.

São **9 combinações × 3 repetições × 4 cenários = 108 execuções válidas**. Tentativas inválidas e recuperações permanecem registradas para auditoria, mas não entram nas estatísticas definitivas.

**Limitação importante:** C1→C3 e C2→C4 alteram simultaneamente vCPUs e workers. Essas comparações não isolam o efeito de cada fator. Houve também uma atualização do Ubuntu durante a campanha, registrada como possível fator de confusão.

## Instalação

Requisitos: Python 3.10 ou superior, `venv`, `pip`, Git e, para a execução distribuída, VirtualBox e OpenSSH. Crie **ambientes virtuais separados** no Windows e no Ubuntu; não copie o `.venv` entre sistemas.

**Na VM Ubuntu (APIs e monitoramento):**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-monitoramento.txt
```

**No Windows PowerShell (Locust, análise e testes):**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-carga.txt -r requirements-analise.txt
```

## Execução das APIs no Ubuntu

Execute a partir da raiz do projeto, com o ambiente virtual instalado. Os exemplos abaixo correspondem aos cenários **C1/C2 (1 worker)**. Para **C3/C4**, use `--workers 2` nas três aplicações.

Em terminais separados:

```bash
CPU_DIAGNOSTICO=1 python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 1
```

```bash
POI_APLICACAO=memoria POI_DIAGNOSTICO=1 MEMORY_RETENCAO_SEGUNDOS=1 python -m uvicorn scripts.monitoramento.servidor_experimental:criar_app --factory --host 0.0.0.0 --port 8002 --workers 1
```

```bash
POI_APLICACAO=io POI_DIAGNOSTICO=1 IO_FSYNC=1 python -m uvicorn scripts.monitoramento.servidor_experimental:criar_app --factory --host 0.0.0.0 --port 8003 --workers 1
```

A partir do Windows, após configurar o redirecionamento NAT das portas 8001–8003:

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe http://127.0.0.1:8002/health
curl.exe http://127.0.0.1:8003/health
```

O procedimento completo de coleta foi automatizado por `scripts/experimentacao/orquestrar.py`, executado **no Windows**. A ferramenta audita o ambiente da VM via SSH, inicia o monitoramento Linux, executa o Locust no host, transfere os arquivos por SCP e consolida os resultados. **Não execute novamente a campanha definitiva apenas para consultar os resultados existentes.**

## Testes automatizados

No Windows, a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

A suíte cobre as APIs, a coleta, as validações, o orquestrador e as rotinas de análise. A última execução informada durante a conclusão do projeto aprovou **373 testes** (com aviso de depreciação Starlette/HTTPX).

## Resultados e gráficos

As análises definitivas estão em:

```text
experimentos/resultados/analise_final/
├── C1/
├── C2/
├── C3/
├── C4/
└── comparativo_C1_C4/
    ├── relatorio.md
    ├── comparativos.csv
    ├── tabelas.csv
    ├── diferencas.csv
    ├── fontes.json
    └── *.png / *.svg
```

[**Abrir relatório comparativo C1–C4**](experimentos/resultados/analise_final/comparativo_C1_C4/relatorio.md)

Gráficos principais: [vazão CPU](experimentos/resultados/analise_final/comparativo_C1_C4/cpu_vazao.png), [latência CPU](experimentos/resultados/analise_final/comparativo_C1_C4/cpu_latencia.png), [memória residente](experimentos/resultados/analise_final/comparativo_C1_C4/memoria_memoria.png) e [escrita em disco](experimentos/resultados/analise_final/comparativo_C1_C4/io_disco.png).

**Síntese:** com dois usuários CPU-bound, a passagem de C1 para C3 apresentou aumento de aproximadamente **120,7% na vazão**; o aumento isolado de RAM não apresentou ganho uniforme; a aplicação Memory-bound demonstrou crescimento do RSS com a concorrência; o perfil I/O-bound não apresentou melhoria uniforme com mais vCPUs/workers.

Os resultados são **descritivos**, baseados em três repetições por combinação. Desvios-padrão não são intervalos de confiança; p95 agregado não equivale ao p95 de todas as requisições reunidas. Os contadores de disco refletem a VM, não exclusivamente a API ou a escrita física do host.

## Estrutura do projeto

```text
apps/                     # APIs CPU, memória e I/O
scripts/carga/            # Locust e captura das requisições
scripts/monitoramento/    # Monitor Linux e verificações de relógio
scripts/experimentacao/   # Orquestração e auditoria da VM
scripts/analise/          # Consolidação e comparação estatística
tests/                    # Testes automatizados
docs/                     # Diagnósticos e documentação complementar
experimentos/resultados/  # Dados e análises experimentais
```

Os arquivos originais e as tentativas históricas devem ser preservados. Para detalhes sobre protocolo, limitações, métricas e recuperações, consulte os relatórios de `analise_final/`, os manifestos de orquestração e os documentos em `docs/`.
