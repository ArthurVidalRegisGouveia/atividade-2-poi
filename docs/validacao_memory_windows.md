# Validação experimental da aplicação Memory-bound no Windows

Execução real em 08/10/2026, das 08:39:24 às 08:40:07 (America/Sao_Paulo,
UTC-03:00), com duração total de 42,618 segundos, incluindo aquecimento.

## Ambiente e método

- Python 3.14.3 de 64 bits, FastAPI 0.142.4 e Uvicorn 0.54.0.
- Um trabalhador Uvicorn, PID real 12812, em `127.0.0.1:8002`.
- `TEMP` e `TMP` configurados para `.temp` na unidade D: somente nos
  processos de execução do experimento e dos testes. Fora dessas sessões,
  ambos permaneceram no diretório temporário anterior da unidade C:.
- Pedido de aquecimento de 1 MiB; depois, três repetições de um pedido de
  50 MiB seguido de dois pedidos simultâneos de 50 MiB.
- Retenção de cinco segundos após a escrita/verificação; máximo de duas
  alocações simultâneas, totalizando 100 MiB de regiões tocadas.
- Coleta externa ao servidor via `GetProcessMemoryInfo`: `WorkingSetSize`
  (memória residente) e `PrivateUsage` (memória privada comprometida).
- `GlobalMemoryStatusEx` para memória física total e disponível do sistema.
- Amostragem solicitada a cada 0,05 segundo, com 602 amostras durante a carga.
  Os timestamps efetivos e os contadores em bytes estão no JSON. Os picos
  informados são máximos amostrados, não máximos contínuos garantidos.
- Tempos HTTP medidos com `time.perf_counter`, incluindo rede local,
  processamento, retenção e leitura da resposta. Uma barreira sincronizou
  o envio dos pares de requisições.
- Medição após cada ciclo imediatamente e novamente um segundo depois.
- O script recusa iniciar uma fase com menos de 512 MiB de RAM disponível.

As aplicações não foram modificadas. Os hashes SHA-256 antes e depois coincidiram:

```text
CPU-bound:    933C2693DDECB2C340A81040BBD2A79780A1E6CF61EF8C089E5840A9527125AA
Memory-bound: 6C325FC100AFC22058CE5737A8B5283D1C74B9FEDE653939BE94611D00880A4B
```

## Memória residente do processo

Todas as medidas abaixo são reais, expressas em MiB e arredondadas para três
casas. A linha de base inicial após aquecimento foi **51,113 MiB**.

| Repetição | Pedidos simultâneos | Antes | Pico amostrado | Aumento no pico | Após 1 segundo |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 51,113 | 101,172 | 50,059 | 51,180 |
| 1 | 2 | 51,180 | 151,332 | 100,152 | 51,352 |
| 2 | 1 | 51,352 | 101,422 | 50,070 | 51,430 |
| 2 | 2 | 51,430 | 151,578 | 100,148 | 51,578 |
| 3 | 1 | 51,578 | 101,645 | 50,066 | 51,645 |
| 3 | 2 | 51,645 | 151,793 | 100,148 | 51,793 |

Em todos os ciclos, a leitura imediatamente após as respostas já era igual à
leitura um segundo depois. O pico máximo observado foi 151,793 MiB.

## Tempos, sobreposição e erros

| Repetição | Um pedido: duração HTTP (s) | Dois pedidos: durações HTTP (s) | Sobreposição dos intervalos HTTP (s) |
| --- | ---: | --- | ---: |
| 1 | 5,0283 | 5,0480 / 5,0280 | 5,0277 |
| 2 | 5,0274 | 5,0273 / 5,0490 | 5,0273 |
| 3 | 5,0272 | 5,0526 / 5,0458 | 5,0455 |

Em cada cenário de dois pedidos houve 99 amostras com aumento residente
superior a 90 MiB sobre a linha de base daquele ciclo. Os intervalos entre
a primeira e a última dessas amostras foram 4,9372, 4,9348 e 4,9620 segundos.
Esses patamares, combinados com os pedidos concorrentes e os testes de
sobreposição dos mapeamentos, sustentam a conclusão de alocações sobrepostas.
Os intervalos HTTP isoladamente não identificam o instante exato de alocação.

Todos os nove pedidos medidos retornaram HTTP 200 e:

```json
{"tipo":"Memory-bound","tamanho_mb":50,"verificacao":12801}
```

Não houve erros no experimento. O log stderr do servidor ficou vazio. O processo
iniciado pelo script foi encerrado e seu PID não estava ativo na conferência.
A retenção explica a maior parte dos tempos HTTP e não deve ser interpretada
como tempo necessário para alocar ou acessar 50 MiB de RAM.

## Liberação e crescimento residual

A memória residente caiu após todas as cargas. Não houve retenção acumulada
dos blocos de 50 ou 100 MiB entre ciclos. Entretanto, a linha de base cresceu
gradualmente de **51,113 para 51,793 MiB**, diferença de **0,680 MiB**.
A memória privada comprometida passou de 41,957 para 42,551 MiB, diferença de
0,594 MiB. Estes contadores medem o processo inteiro, não só os mapeamentos.

A origem desse crescimento residual não foi isolada. Três repetições não
permitem assegurar ausência de um vazamento pequeno ou atribuir o crescimento
a um componente específico. Os testes automatizados confirmam fechamento das
regiões `mmap`, inclusive quando há erro, mas não substituem uma análise longa
da memória de todo o processo.

O sistema tinha 16317,742 MiB de RAM física. A memória física disponível foi
5185,047 MiB inicialmente e 5170,090 MiB ao final. A variação do sistema inclui
outros processos e não representa exclusivamente esta API. `PrivateUsage`
mede comprometimento, não RAM privada residente.

## Testes e reprodução

Os **57 testes passaram**: 22 CPU-bound e 35 Memory-bound, em 1,20 segundo.
Houve somente o aviso conhecido do Starlette sobre HTTPX no cliente de testes.
Não foram instalados novos pacotes e nenhum arquivo foi excluído.

Na raiz do projeto, com a porta 8002 livre, reproduza em uma sessão PowerShell
destinada à validação (feche-a ao terminar para descartar suas variáveis):

```powershell
New-Item -ItemType Directory -Path .temp -Force
$env:TEMP = (Resolve-Path .temp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe scripts\monitoramento\verificar_memoria_windows.py
.\.venv\Scripts\python.exe -m pytest -v
```

O script cria um JSON com nome único e um log stderr em `.temp`, sem sobrescrever
resultados existentes. Esses arquivos documentam a execução; não simulam RAM.

Arquivos desta execução:

- [Amostras e metadados completos](../experimentos/resultados/publicados/memory_windows_20261008_083924_884107.json).
- [Saída do pytest](../experimentos/resultados/publicados/pytest_memory_windows_20261008_083924.txt).
- Log vazio: `.temp/uvicorn_memory_20261008_083924_884107.stderr.log`.

O ensaio confirmou ocupação temporária observável de RAM, sobreposição e
liberação das grandes regiões no Windows. A validação na VM Ubuntu com 1 GB e
a investigação de desempenho sob pressão de memória permanecem etapas futuras.

As cópias publicadas normalizam caminhos locais e usam UTF-8. Os originais foram
preservados localmente, sem alteração dos resultados numéricos.
