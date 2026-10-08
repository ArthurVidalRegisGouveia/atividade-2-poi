# Validação experimental local da aplicação I/O-bound

Execução real em 08/10/2026, de 09:00:14 a 09:00:48, America/Sao_Paulo
(UTC-03:00). As três aplicações permaneceram intactas: os hashes SHA-256
anteriores e posteriores coincidem e estão registrados no JSON.

## Configuração e segurança

- Python 3.14.3 de 64 bits, FastAPI 0.142.4 e Uvicorn 0.54.0.
- Um trabalhador Uvicorn em `127.0.0.1:8003`, sem `reload`.
- PID 13172 para `IO_FSYNC=0`; servidor reiniciado, PID 9944 para `IO_FSYNC=1`.
- `IO_TAMANHO_MAX_MB=32`, `IO_OPERACOES_MAX=5` e `IO_MAX_SIMULTANEAS=1`.
- Blocos de 64 KiB, sem alterações na lógica da API.
- Diretório exclusivo na unidade D: `.temp/io_validation_20261008_090014_236514`.
- Espaço livre antes da carga: 328494624768 bytes (305,934 GiB).
- Cada fase é recusada se houver menos de 1 GiB livre. O maior arquivo ativo
  nesta execução foi de 10 MiB; os pedidos foram sequenciais.
- Os doze pedidos medidos escreveram 213 MiB e leram 213 MiB lógicos ao todo.
  Houve também um aquecimento de 1 MiB em cada configuração, registrado à parte.
- `TEMP` e `TMP` apontaram para `.temp` em D: somente nos processos de validação
  e testes. Fora dessas sessões, ambos permaneceram no diretório temporário
  anterior da unidade C:.
- Nenhum arquivo preexistente foi apagado, nenhuma dependência foi instalada e
  nenhuma configuração permanente do Windows foi modificada.

## Tempos individuais e médias

Tempos HTTP completos medidos com `time.perf_counter` ao redor de `urlopen` e
da leitura/decodificação da resposta. Incluem rede local e processamento HTTP.
Consultas de contadores e a espera externa de observação ficam fora do cronômetro.
Valores reais em milissegundos, arredondados para três casas:

| Cenário | MiB por arquivo | Operações | fsync | Repetição 1 | Repetição 2 | Repetição 3 | Média |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 | 1 | 1 | 0 | 5,193 | 4,405 | 16,438 | 8,679 |
| T2 | 10 | 1 | 0 | 11,453 | 30,234 | 33,824 | 25,170 |
| T3 | 10 | 1 | 1 | 225,144 | 149,569 | 158,803 | 177,839 |
| T4 | 10 | 5 | 1 | 680,715 | 787,990 | 664,143 | 710,949 |

Todos os doze pedidos retornaram **HTTP 200**, verificação **`ok`** e os seguintes
bytes lógicos, iguais nas três repetições de cada cenário:

| Cenário | Bytes escritos pela API | Bytes lidos pela API | Bytes processados pela API |
| --- | ---: | ---: | ---: |
| T1 | 1048576 | 1048576 | 2097152 |
| T2 | 10485760 | 10485760 | 20971520 |
| T3 | 10485760 | 10485760 | 20971520 |
| T4 | 52428800 | 52428800 | 104857600 |

## Origem e interpretação dos contadores

Foram coletados dois níveis distintos:

1. **Processo:** `GetProcessIoCounters`, usando o PID real do servidor. Os deltas
   `ReadTransferCount` e `WriteTransferCount` coincidiram com os bytes lidos e
   escritos informados pela API em todos os pedidos. Os contadores incluem I/O
   do processo inteiro; não comprovam transferências físicas no dispositivo.
   Foram observadas 9/8 operações de leitura/escrita em T1, 81/80 em T2 e T3,
   e 405/400 em T4. Essas contagens do Windows não correspondem ao parâmetro
   `operacoes`, que representa ciclos completos de arquivos.
   [Referência Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getprocessiocounters).
2. **Volume D:** `Get-CimInstance Win32_PerfRawData_PerfDisk_LogicalDisk`, instância
   `D:`. Foram subtraídos os contadores acumulados antes e depois; os nomes
   `DiskReadBytesPersec`/`DiskWriteBytesPersec` na classe RAW não são taxas já
   formatadas. A tabela apresenta deltas em bytes convertidos para MiB, não MiB/s.
   [Referência sobre contadores RAW](https://learn.microsoft.com/en-us/windows/win32/perfctrs/about-performance-counters).

O sandbox negou a consulta CIM. Após liberação, o script foi executado fora dele
para obter os contadores, sem modificar o sistema. A janela do volume começa
antes do pedido e termina após uma espera externa de um segundo e a consulta
seguinte. Os timestamps reais do provedor resultaram em janelas de 1,573 a
2,435 segundos. Essa janela difere da duração HTTP e inclui atividade de outros
processos. A espera é apenas de observação e não existe no endpoint.

Atividade real registrada no volume D:, por janela:

| Cenário/repetição | Leitura (MiB) | Escrita (MiB) | Operações de leitura | Operações de escrita |
| --- | ---: | ---: | ---: | ---: |
| T1/1 | 0,000000 | 0,152344 | 0 | 7 |
| T1/2 | 0,000000 | 0,070313 | 0 | 6 |
| T1/3 | 0,000000 | 0,199219 | 0 | 14 |
| T2/1 | 0,062500 | 0,070313 | 1 | 6 |
| T2/2 | 0,000000 | 0,171875 | 0 | 5 |
| T2/3 | 0,000000 | 0,003906 | 0 | 1 |
| T3/1 | 0,000000 | 10,148438 | 0 | 16 |
| T3/2 | 0,000000 | 10,035156 | 0 | 14 |
| T3/3 | 0,187500 | 10,085938 | 3 | 14 |
| T4/1 | 0,000000 | 50,183594 | 0 | 65 |
| T4/2 | 0,003906 | 50,718750 | 1 | 147 |
| T4/3 | 0,000000 | 50,179688 | 0 | 65 |

Há evidência de operações de armazenamento contabilizadas pelo Windows no
volume. Não houve medição exclusiva de I/O físico da API na mídia do dispositivo.
Esses contadores não isolam metadados, outras aplicações nem caches do hardware,
e não comprovam a persistência de cada byte em uma mídia física específica.

## Interpretação do comportamento

A média aumentou de 8,679 ms para 25,170 ms ao passar de 1 para 10 MiB sem
sincronização: aproximadamente 2,90 vezes, apesar de dez vezes mais dados.
Há variação entre repetições, incluindo T1/3 mais lento que T2/1; os resultados
não sustentam uma relação linear ou uma taxa máxima de desempenho do hardware.

Para o mesmo tamanho de 10 MiB e uma operação, habilitar `fsync` elevou a média
de 25,170 para 177,839 ms, cerca de 7,07 vezes. A escrita observada no volume
também aumentou para cerca de 10 MiB por janela. Isso é consistente com o custo
de solicitar sincronização, embora a ordem dos cenários e outras cargas não
tenham sido controladas como em um benchmark rigoroso.

Com cinco operações sincronizadas, a média foi 710,949 ms, cerca de quatro vezes
a de uma operação sincronizada, para cinco vezes mais bytes lógicos. Cada
operação escreve e lê um novo arquivo; não são cinco pedidos concorrentes.

As leituras contabilizadas no volume foram nulas ou muito menores que as
leituras lógicas da API. Esse resultado é consistente com leitura atendida pelo
cache após a escrita. Com `fsync=0`, os arquivos são removidos logo após o
processamento, e os deltas de escrita do volume foram muito inferiores aos
bytes lógicos: não se pode concluir que todo conteúdo atingiu o dispositivo.
`fsync` não esvazia o cache de leitura. Não houve limpeza global de caches,
alteração de políticas do disco ou teste de leitura com cache frio.

## Limpeza, erros e testes

A pasta exclusiva estava vazia antes e depois de cada uma das doze execuções,
após os aquecimentos e ao final. Nenhum arquivo da aplicação permaneceu.
Os dois logs stderr estavam vazios. Ambos os servidores foram encerrados;
seus PIDs não estavam ativos na conferência. Não houve erro HTTP, de integridade,
de armazenamento ou de coleta registrado nesta execução.

Espaço livre ao final: 329472098304 bytes. A diferença de espaço livre do volume
inclui outros processos e não é uma medida de bytes escritos pela API.

Os **101 testes automatizados passaram**, sem falhas: 22 CPU-bound,
35 Memory-bound e 44 I/O-bound, em 2,27 segundos. Houve apenas o aviso conhecido
do Starlette sobre a descontinuação de HTTPX no cliente de testes.

## Artefatos e reprodução

- [JSON com respostas, contadores, timestamps, médias, PIDs e hashes](../experimentos/resultados/publicados/io_windows_20261008_090014_236514.json).
- [Saída completa dos testes](../experimentos/resultados/publicados/pytest_io_windows_20261008_090014.txt).
- Script: `scripts/monitoramento/verificar_io_windows.py`.

Na raiz, com a porta 8003 livre:

```powershell
$env:TEMP = (Resolve-Path .temp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe scripts\monitoramento\verificar_io_windows.py
.\.venv\Scripts\python.exe -m pytest -v
```

Use uma sessão dedicada para que as variáveis sejam descartadas ao encerrá-la.
O script cria uma pasta exclusiva e registros com nomes únicos; não sobrescreve
resultados antigos nem remove resíduos preexistentes. Se a consulta de disco
for negada em outro ambiente, o JSON preservará a mensagem e não inventará valores.

As cópias publicadas normalizam caminhos locais e usam UTF-8. Os originais foram
preservados localmente, sem alteração dos resultados numéricos.
