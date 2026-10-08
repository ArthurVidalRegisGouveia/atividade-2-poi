# Atividade 2 — Provisionamento e Operação de Infraestruturas

Projeto acadêmico para comparar aplicações backend CPU-bound, Memory-bound e
I/O-bound em experimentos de demanda, desempenho e provisionamento de recursos.
Os experimentos serão realizados em uma VM Ubuntu Server 22.04 no VirtualBox,
com configurações de 1 e 2 vCPUs.

As três aplicações **CPU-bound**, **Memory-bound** e **I/O-bound** estão
implementadas e são independentes, nas portas 8001, 8002 e 8003.
Os experimentos e a comparação de desempenho na VM são etapas posteriores.

## Requisitos

- Python 3.10 ou superior (compatível com o Python 3.10 do Ubuntu Server 22.04).
- Suporte a ambientes virtuais (`venv`) e pip.
- Git para versionamento.
- curl para os exemplos HTTP.

Execute todos os comandos a partir da raiz do projeto. As dependências são
FastAPI, Uvicorn, pytest e HTTPX; HTTPX é usado pelo cliente de testes.

## Ambiente virtual e instalação

No Ubuntu/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
```

No Windows/PowerShell, é possível usar diretamente o interpretador do ambiente,
sem alterar a política de execução de scripts:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

Nos comandos abaixo, no Windows, substitua `python` por
`.\.venv\Scripts\python.exe`. No Linux, mantenha o ambiente virtual ativo.
Não instale as dependências globalmente.

## Executar a aplicação CPU-bound

Um processo trabalhador, na porta 8001:

```bash
python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 1
```

Dois processos trabalhadores, para os experimentos com 2 vCPUs:

```bash
python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 2
```

Interrompa o servidor anterior com Ctrl+C antes de iniciar outro na mesma porta.
O Uvicorn gerencia os processos; a aplicação não cria processos por requisição.
Evite `--reload` durante as medições e registre o número de trabalhadores em
cada experimento. Dois trabalhadores também podem ser testados com 1 vCPU para
avaliar a disputa pelo recurso.

## Endpoints e exemplos

```bash
curl http://localhost:8001/health
curl "http://localhost:8001/primos?limite=10"
curl "http://localhost:8001/primos?limite=100000"
curl "http://localhost:8001/primos?limite=0"
```

No PowerShell, use `curl.exe` para executar o curl, evitando o alias de versões
antigas do PowerShell.

`GET /health` retorna HTTP 200 e `{"status":"ok"}`.

`GET /primos?limite=10` retorna HTTP 200:

```json
{"tipo":"CPU-bound","limite":10,"quantidade_primos":4}
```

A contagem inclui o limite se ele for primo. Sem o parâmetro, o limite padrão é
100000, que resulta em 9592 primos. Valores negativos, zero, texto, valores
fracionários e limites acima do máximo retornam HTTP 422 com detalhes de validação.

### Limite configurável

`CPU_LIMITE_MAX` define o máximo permitido; o valor padrão é 1000000. O mínimo
permitido é 1. Configure a variável antes de iniciar o servidor:

```bash
export CPU_LIMITE_MAX=200000
python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 1
```

No PowerShell:

```powershell
$env:CPU_LIMITE_MAX = "200000"
.\.venv\Scripts\python.exe -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 1
```

A variável deve conter um inteiro positivo; uma configuração inválida impede a
inicialização. Se o máximo for menor que 100000, o limite padrão passa a ser esse
máximo. O teto restringe o trabalho por requisição, mas não limita a quantidade de
requisições simultâneas.

## Decisões técnicas

A contagem utiliza divisão por tentativa: considera o primo 2 separadamente e
testa candidatos ímpares com divisores ímpares até a raiz quadrada inteira.
Não armazena listas de primos ou crivos; o uso de memória auxiliar é constante.
O trabalho é real de CPU, sem pausas artificiais, cache ou aleatoriedade.

O endpoint é síncrono (`def`), e o FastAPI executa esse trabalho em sua pool de
threads. Em CPython convencional, o GIL limita o paralelismo desse cálculo Python
dentro de um processo. Os processos independentes do Uvicorn permitem utilizar
múltiplas vCPUs quando há requisições concorrentes; uma única requisição continua
sendo calculada por um trabalhador. `/health` pode sofrer aumento de latência
sob saturação, o que pode ser observado nos experimentos.

## Executar a aplicação Memory-bound

Na porta 8002, comece com um trabalhador para a VM de 1 GB:

```bash
python -m uvicorn apps.memory_bound.main:app --host 0.0.0.0 --port 8002 --workers 1
```

No Windows/PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.memory_bound.main:app --host 0.0.0.0 --port 8002 --workers 1
```

As três APIs podem funcionar ao mesmo tempo, em terminais separados e nas suas
respectivas portas. Não são necessárias novas dependências.

```bash
curl http://localhost:8002/health
curl "http://localhost:8002/memoria?tamanho_mb=1"
curl "http://localhost:8002/memoria?tamanho_mb=50"
curl "http://localhost:8002/memoria?tamanho_mb=64"
curl "http://localhost:8002/memoria?tamanho_mb=0"
```

No PowerShell, use `curl.exe`. O `/health` retorna `{"status":"ok"}`.
O `/memoria?tamanho_mb=50`, em um sistema com páginas de 4096 bytes, retorna:

```json
{"tipo":"Memory-bound","tamanho_mb":50,"verificacao":12801}
```

O parâmetro é inteiro. Nesta API, **1 MB corresponde a 1 MiB = 1048576 bytes**.
O tamanho padrão é 50; se estiver fora dos limites configurados, é ajustado ao
limite mais próximo. Parâmetros inválidos retornam HTTP 422 antes de alocar.

### Configuração de memória e retenção

Defina as variáveis antes de iniciar o servidor:

| Variável | Padrão | Validação |
| --- | --- | --- |
| `MEMORY_LIMITE_MIN_MB` | `1` | Inteiro positivo, menor ou igual ao máximo |
| `MEMORY_LIMITE_MAX_MB` | `64` | Inteiro positivo; respeita o orçamento abaixo |
| `MEMORY_MAX_SIMULTANEAS` | `4` | Inteiro positivo; respeita o orçamento abaixo |
| `MEMORY_RETENCAO_SEGUNDOS` | `0` | Número finito entre 0 e 5, inclusive |

O produto `MEMORY_LIMITE_MAX_MB * MEMORY_MAX_SIMULTANEAS` não pode ultrapassar
**256 MiB por processo**. Configurações inválidas impedem a inicialização.
O semáforo limita somente as requisições com buffers ativos; os pedidos que
encontrarem todas as vagas ocupadas recebem HTTP 503, sem nova alocação.
Uma falha de alocação que resulte em `MemoryError` também retorna HTTP 503.
Falhas de criação do mapeamento (`OSError`) recebem a mesma resposta.

Para observar dois buffers de 50 MiB simultaneamente, ative uma retenção curta:

```bash
export MEMORY_RETENCAO_SEGUNDOS=2
python -m uvicorn apps.memory_bound.main:app --host 0.0.0.0 --port 8002 --workers 1
```

Em outro terminal Linux, envie as requisições em paralelo:

```bash
curl "http://localhost:8002/memoria?tamanho_mb=50" &
curl "http://localhost:8002/memoria?tamanho_mb=50" &
wait
```

No PowerShell, configure a retenção antes de iniciar:

```powershell
$env:MEMORY_RETENCAO_SEGUNDOS = "2"
.\.venv\Scripts\python.exe -m uvicorn apps.memory_bound.main:app --host 0.0.0.0 --port 8002 --workers 1
```

Envie as requisições em terminais distintos para observar a sobreposição.
Para desativar a retenção na próxima inicialização, configure o valor `0`.

A retenção existe exclusivamente para tornar a ocupação observável e permitir
a sobreposição de pedidos. Ela aumenta a latência HTTP e, sob demanda contínua,
o número de regiões simultaneamente ativas. Registre seu valor em cada execução;
não interprete esses segundos como custo de alocação ou desempenho da RAM. Para
medir o tempo de alocação/acesso sem essa espera, utilize retenção `0`.

### Modelo de execução e liberação

O endpoint síncrono é executado na pool de threads do FastAPI, permitindo manter
buffers de várias requisições simultaneamente. A alocação e a verificação são
feitas antes da retenção. A espera opcional (`sleep`) ocorre somente na thread
da requisição, após o trabalho de memória, preservando o event loop. Sem retenção,
as operações podem terminar rápido demais para observar sobreposição em cargas
pequenas. Esse modelo segue a [documentação de concorrência do FastAPI](https://fastapi.tiangolo.com/async/#path-operation-functions).

Cada requisição cria um `mmap` anônimo (`fileno=-1`) do tamanho solicitado, com
acesso privado copy-on-write (`ACCESS_COPY`), escreve um byte por página do
sistema e também o último byte. A verificação soma os bytes escritos,
incluindo o último byte separadamente. O resultado é
`ceil(tamanho_em_bytes / tamanho_da_pagina) + 1` e depende do tamanho de página
da plataforma (`mmap.PAGESIZE`). Não existem cópias completas, hashes pesados
ou laços sobre cada byte. O teste exercita capacidade/ocupação de memória;
não é um benchmark de largura de banda com varredura integral do buffer.

As escritas provocam o acesso efetivo às páginas, evitando medir somente reserva
virtual. O sistema operacional ainda pode mover páginas para swap; portanto,
acompanhe também a memória residente e a atividade de swap nos experimentos.

O contexto `with` fecha explicitamente o mapeamento, retirando a região do
espaço de endereçamento do processo, antes de retornar a resposta e também em
caso de erro. O bloco `finally` devolve a vaga. Isso evita depender da liberação
de um grande buffer pelo alocador de objetos do Python ou pelo coletor de lixo.
Um objeto fechado pode continuar referenciado, mas a região já foi desmapeada.
Não há armazenamento global das regiões. O RSS total inclui Python, bibliotecas
e threads, e não precisa voltar exatamente ao valor inicial.

Não há arquivo de dados, `flush`, escrita em disco, hash pesado ou cópia integral
para simular RAM. A infraestrutura de memória virtual do sistema pode usar
pagefile/swap sob pressão; isso é comportamento do sistema operacional, não uma
operação de I/O da aplicação. Mapeamentos anônimos e seu fechamento estão
descritos na [documentação Python](https://docs.python.org/3/library/mmap.html).

Na VM de 1 GB, o teto de 256 MiB reserva espaço para Ubuntu, Python e outros
serviços, mas não é um limite do RSS total nem uma garantia contra OOM sob outras
cargas. Comece com um trabalhador e observe a memória disponível. O orçamento
e o semáforo são **por processo**: dois trabalhadores podem manter até 512 MiB
de buffers, além da memória de cada processo. Evite aumentar trabalhadores sem
reavaliar esse consumo. O teto também não é compartilhado com a API CPU-bound.

### Medir a memória do processo e a memória do sistema

Use um trabalhador, sem `--reload`. Identifique o PID na mensagem do Uvicorn
`Started server process [PID]`. Monitore esse processo, não o terminal, o launcher
do ambiente virtual ou o supervisor de múltiplos trabalhadores.

| Medida | Windows | Linux | Interpretação |
| --- | --- | --- | --- |
| RAM residente do processo | Conjunto de trabalho / working set | RSS / `VmRSS` | Páginas do processo atualmente em RAM, incluindo páginas compartilhadas |
| RAM privada residente | Conjunto de trabalho privado | `Private_Clean` + `Private_Dirty` em `smaps_rollup` | Páginas residentes privadas; deve crescer com as escritas desta API |
| Memória privada comprometida | Tamanho de confirmação / commit size | Sem equivalência direta; `VmSize` é espaço virtual | Comprometimento não significa presença integral em RAM |
| Memória do sistema | Desempenho → Memória | `free -m`, `/proc/meminfo` | Todos os processos, kernel e caches; não identifica o consumo desta API |

No Windows, abra o **Gerenciador de Tarefas → Detalhes**, encontre o PID e
habilite as colunas de conjunto de trabalho, conjunto de trabalho privado e
tamanho de confirmação (os nomes podem variar conforme a versão). Compare com
a aba **Desempenho → Memória**, que descreve o sistema inteiro. As páginas
escritas com copy-on-write tornam-se privadas, como descrito na
[documentação Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile).

No PowerShell, uma amostra equivalente para o processo é:

```powershell
$servidorPid = 1234  # Substitua pelo PID real indicado pelo Uvicorn.
Get-Process -Id $servidorPid | Select-Object Id,
    @{Name="ResidenteMiB"; Expression={$_.WorkingSet64 / 1MB}},
    @{Name="PrivadaComprometidaMiB"; Expression={$_.PrivateMemorySize64 / 1MB}}
```

`PrivateMemorySize64` mede memória privada comprometida, não o conjunto de
trabalho privado. Não confunda esse contador com RAM física residente.

Na VM Ubuntu, use o PID do Python **dentro da VM**:

```bash
servidor_pid=1234  # Substitua pelo PID real.
watch -n 0.5 "ps -p $servidor_pid -o pid,rss,vsz,cmd"
```

Em outros terminais, consulte a memória privada/residente e o sistema:

```bash
cat /proc/$servidor_pid/smaps_rollup
cat /proc/$servidor_pid/status
free -m
vmstat 1
```

Em `ps`, RSS e VSZ são expressos em KiB; RSS/1024 resulta em MiB. Use `Rss`,
`Private_Dirty`, `Pss` e `Swap` de `smaps_rollup` para distinguir residência,
páginas privadas, divisão proporcional de páginas compartilhadas e paginação.
Observe `available` no `free` e `si`/`so` no `vmstat`. A documentação do
[`/proc` no kernel Linux](https://docs.kernel.org/filesystems/proc.html) descreve
esses contadores. No host Windows, a memória do processo VirtualBox representa
a VM inteira; ela não isola o consumo da API no Ubuntu.

Procedimento para confirmar alocação e liberação:

1. Inicie a API com `MEMORY_RETENCAO_SEGUNDOS=5` e um trabalhador.
2. Faça um pedido pequeno de aquecimento e registre a memória do processo ocioso.
3. Envie um pedido de 50 MiB e observe o aumento durante os cinco segundos de
   retenção; espere a resposta e registre a memória novamente.
4. Envie dois pedidos de 50 MiB ao mesmo tempo. Enquanto ambos estiverem retidos,
   espere cerca de 100 MiB adicionais de RAM privada/residente, além da linha
   de base. O tamanho virtual/comprometido pode apresentar outro incremento.
5. Após as respostas, a parcela dos mapeamentos deve desaparecer. Repita a carga
   para verificar que os picos se repetem sem crescimento acumulado dessas regiões.
6. Registre separadamente o uso do sistema: sua variação pode ser diferente por
   causa de caches, outros processos, compressão e swap. Se houver paginação,
   não espere que todo o tamanho solicitado apareça no RSS simultaneamente.

Há também um experimento automatizado Windows, sem dependências adicionais:

```powershell
.\.venv\Scripts\python.exe scripts\monitoramento\verificar_memoria_windows.py
```

Execute com a porta 8002 livre. O script inicia seu próprio servidor local com
um trabalhador e retenção de cinco segundos, faz aquecimento e repete três vezes
um pedido de 50 MiB seguido de dois pedidos concorrentes de 50 MiB.
Registra JSON com PID, memória residente/comprometida do processo e
memória física total/disponível do sistema, antes, durante e após os pedidos.
Ele amostra o processo a cada 0,05 segundo durante a carga, registra os tempos
HTTP e encerra somente o servidor que iniciou. Recusa a carga se houver menos
de 512 MiB de RAM física disponível. O JSON tem nome único em
`experimentos/resultados`, e o log stderr fica em `.temp`, ignorada pelo Git.
Esses registros não são usados para simular consumo de RAM.
As métricas vêm das APIs nativas do Windows, não de contadores internos da API.

Para direcionar os temporários desta sessão para D:, sem alterar a configuração
global do Windows, execute em uma sessão PowerShell dedicada:

```powershell
New-Item -ItemType Directory -Path .temp -Force
$env:TEMP = (Resolve-Path .temp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe scripts\monitoramento\verificar_memoria_windows.py
.\.venv\Scripts\python.exe -m pytest -v
```

Feche essa sessão ao terminar. A alteração das variáveis vale somente para ela
e seus processos filhos.

## Executar a aplicação I/O-bound

A API cria arquivos reais, escreve e lê em blocos fixos de 64 KiB e compara
os dados com um padrão determinístico. A comparação de bytes evita hashes ou
cálculos pesados. A aplicação não usa `sleep` e não carrega o arquivo inteiro
na RAM. Não são necessárias novas dependências: usa FastAPI, Uvicorn e a
biblioteca padrão Python; os testes usam pytest e HTTPX já instalados.

Na raiz do projeto, com o ambiente virtual ativo no Ubuntu/Linux:

```bash
python -m uvicorn apps.io_bound.main:app --host 0.0.0.0 --port 8003 --workers 1
```

No Windows/PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.io_bound.main:app --host 0.0.0.0 --port 8003 --workers 1
```

Exemplos HTTP (no PowerShell, use `curl.exe`):

```bash
curl http://localhost:8003/health
curl "http://localhost:8003/arquivo?tamanho_mb=10&operacoes=1"
curl "http://localhost:8003/arquivo?tamanho_mb=1&operacoes=2"
curl "http://localhost:8003/arquivo?tamanho_mb=0&operacoes=1"
```

O `/health` retorna HTTP 200 e `{"status":"ok"}`. Um pedido padrão retorna:

```json
{
  "tipo": "I/O-bound",
  "tamanho_mb": 10,
  "operacoes": 1,
  "bytes_escritos": 10485760,
  "bytes_lidos": 10485760,
  "bytes_processados": 20971520,
  "verificacao": "ok"
}
```

`tamanho_mb` representa MiB: 1 MiB = 1048576 bytes. `bytes_processados` é a soma
dos bytes escritos e lidos em todas as operações, no nível da aplicação.
São bytes lógicos de arquivo; não representam tráfego físico medido no disco.
Cada operação cria, escreve, verifica e remove um novo arquivo, antes da próxima.

### Configuração de I/O

Configure as variáveis antes de iniciar o Uvicorn:

| Variável | Padrão | Uso |
| --- | --- | --- |
| `IO_DIRETORIO_TEMP` | `.temp/io_bound` | Pasta dedicada aos arquivos da API |
| `IO_TAMANHO_MAX_MB` | `32` | Máximo por arquivo em MiB; inteiro positivo |
| `IO_OPERACOES_MAX` | `5` | Máximo de operações por pedido; inteiro positivo |
| `IO_MAX_SIMULTANEAS` | `2` | Máximo de pedidos com arquivos ativos por processo |
| `IO_FSYNC` | `0` | `0` desativa; `1` solicita sincronização após cada escrita |

Os parâmetros HTTP têm mínimo 1. O tamanho padrão é 10 MiB, ajustado ao máximo
caso o teto configurado seja menor; a quantidade padrão é uma operação.
Configurações inválidas impedem a inicialização. Para manter volumes controlados:

- `IO_TAMANHO_MAX_MB * IO_MAX_SIMULTANEAS` deve ser no máximo 128 MiB.
- `IO_TAMANHO_MAX_MB * IO_OPERACOES_MAX` deve ser no máximo 160 MiB escritos
  por requisição, mais a mesma quantidade lida.

Os dois limites são por processo, não um limite global de uso ou uma reserva de
espaço livre. Outros serviços também consomem armazenamento. Com os padrões,
no máximo dois arquivos de 32 MiB ficam ativos por processo. Mais trabalhadores
multiplicam esse consumo potencial; comece com um trabalhador nos experimentos.

Caminhos relativos são resolvidos contra a raiz do projeto. No Windows atual,
o padrão é `D:\atividade-2-poi\.temp\io_bound`, sem usar C: para os arquivos da API.
No Ubuntu, corresponde à pasta `.temp/io_bound` da cópia do projeto na VM.
A pasta é criada na inicialização do servidor, se necessário. A raiz de uma
unidade é recusada. Use uma pasta própria com permissões de criação e remoção;
a aplicação não altera permissões nem usa diretórios protegidos do Windows.

O endpoint síncrono roda em threads, permitindo I/O concorrente sem executar
essas operações diretamente no event loop. A criação exclusiva de
`NamedTemporaryFile` evita colisões de nomes; escrita e leitura usam o mesmo
handle, compatível com Windows. O contexto fecha e remove somente o arquivo
criado pela operação, inclusive quando escrita, leitura ou integridade falham.
Arquivos preexistentes e a própria pasta são preservados. Esse comportamento
segue a [documentação de temporários Python](https://docs.python.org/3/library/tempfile.html).

Entradas inválidas retornam HTTP 422 antes de criar um arquivo. Saturação de
vagas retorna 503, falhas de integridade retornam 500 e falhas de I/O retornam
507. Falhas do sistema que impeçam a remoção ou encerramentos forçados podem
deixar resíduos; a aplicação não tenta apagar arquivos de requisições anteriores.

### Cache, flush e fsync

Após a escrita, `flush()` transfere o buffer Python para o sistema operacional.
Isso não comprova escrita física no dispositivo. Com `IO_FSYNC=1`, a API chama
`os.fsync()` depois de `flush()`, solicitando sincronização da escrita pelo
sistema operacional, o que pode aumentar a latência. Consulte a
[documentação de `os.fsync`](https://docs.python.org/3/library/os.html#os.fsync).

Mesmo com sincronização, a leitura logo após a escrita pode ser atendida pelo
cache de páginas. O cache do dispositivo, do host e da VM também influencia
os resultados. `fsync` não produz uma leitura com cache frio nem isola a latência
do hardware. Registre sua configuração e meça a atividade real do dispositivo
se o objetivo for avaliar I/O físico. Não esvazie caches globais ou desative
proteções do sistema nesta validação funcional.

### Validação experimental inicial no Windows

Em uma sessão PowerShell dedicada, configure temporários e inicie a API:

```powershell
New-Item -ItemType Directory -Path .temp -Force
$env:TEMP = (Resolve-Path .temp).Path
$env:TMP = $env:TEMP
$env:IO_DIRETORIO_TEMP = Join-Path $env:TEMP "io_bound"
$env:IO_FSYNC = "0"
.\.venv\Scripts\python.exe -m uvicorn apps.io_bound.main:app --host 127.0.0.1 --port 8003 --workers 1
```

Em outro terminal, confira o diretório antes e após um pedido pequeno:

```powershell
Get-ChildItem -LiteralPath .temp\io_bound -Force
curl.exe -sS -w "`nTempo HTTP: %{time_total}s`n" "http://localhost:8003/arquivo?tamanho_mb=1&operacoes=1"
Get-ChildItem -LiteralPath .temp\io_bound -Force
```

O pedido deve indicar 1048576 bytes escritos, 1048576 lidos e verificação `ok`.
Os arquivos `io_bound_*.tmp` dessa requisição devem desaparecer após a resposta.
Durante a execução podem aparecer brevemente; pedidos rápidos podem terminar
antes de uma atualização da listagem. Não adicione pausas artificiais para
tornar esses arquivos visíveis. Os testes de concorrência controlam essa
observação com eventos apenas no código de teste.

Para uma comparação pequena e controlada, registre o PID mostrado pelo Uvicorn,
o tempo HTTP e a atividade no Monitor de Recursos do Windows (aba Disco).
Faça pedidos de 1, 2 e 10 MiB, com uma operação, separadamente. Para concorrência,
envie dois pedidos pequenos em terminais diferentes. Reinicie o servidor com
`IO_FSYNC=1` para comparar a sincronização, preservando as demais condições.
Registre tamanho, operações, trabalhadores, diretório/unidade e estado de cache.
A leitura rápida via cache e o curto volume de escrita podem resultar em pouca
atividade física observável; esse resultado deve constar do relatório.
Interrompa com Ctrl+C ao terminar e confira a pasta, sem excluir outros arquivos.

A validação local T1–T4 foi executada em 08/10/2026, com três repetições por
cenário e um trabalhador. As médias HTTP foram 8,679 ms (1 MiB, uma operação,
fsync=0), 25,170 ms (10 MiB, uma operação, fsync=0), 177,839 ms (10 MiB, uma
operação, fsync=1) e 710,949 ms (10 MiB, cinco operações, fsync=1).
Todos os pedidos retornaram HTTP 200 e deixaram a pasta vazia. Foram coletados
contadores lógicos do processo e contadores de armazenamento do volume D:,
com limitações de atribuição e cache documentadas no
[relatório experimental de I/O](docs/validacao_io_windows.md).

Para repetir essa validação pequena, com a porta 8003 livre:

```powershell
.\.venv\Scripts\python.exe scripts\monitoramento\verificar_io_windows.py
```

O script configura temporários em D: somente para seus processos, verifica o
espaço livre, inicia um trabalhador, reinicia ao alterar `IO_FSYNC` e registra
tempos, respostas, limpeza e contadores em um JSON com nome único. As consultas
CIM podem exigir execução fora de um sandbox. Sem acesso, a indisponibilidade
é registrada como tal, sem substituir os contadores por estimativas.

## Testes

Com as configurações padrão das três aplicações:

```bash
python -m pytest -v
```

No Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Os testes cobrem saúde da aplicação, contagens conhecidas, limite padrão,
determinismo, parâmetros inválidos, configuração do limite máximo e formato JSON.
Não precisam de um servidor Uvicorn em execução.

Para Memory-bound, também verificam diferentes tamanhos (1, 2, 10, 50 e 64 MiB),
escrita/leitura por página, limites mínimo/máximo, retenção após o processamento,
sobreposição real de dois buffers, resposta 503 quando não há vagas, liberação
dos mapeamentos após requisições repetidas e liberação de vagas em caso de erro.
A liberação é verificada por `mmap.closed` mesmo mantendo os objetos referenciados,
incluindo falhas na escrita/verificação e na retenção. A retenção é controlada por eventos
nos testes concorrentes, para observar os buffers sem esperas arbitrárias.

Na etapa anterior à I/O-bound, 57 testes passaram (22 CPU-bound e 35 Memory-bound)
no Windows com Python 3.14.3;
`python -m pip check` não identificou dependências incompatíveis. O Starlette
instalado emitiu um aviso de descontinuação sobre HTTPX no cliente de testes,
sem falhas. A execução na VM Ubuntu ainda precisa ser verificada.

A validação experimental Windows foi concluída em 08/10/2026 com temporários
direcionados para D:. A memória residente inicial foi 51,113 MiB; os picos na
primeira repetição foram 101,172 MiB com um pedido e 151,332 MiB com dois pedidos.
Após três repetições de ambos os cenários, caiu para 51,793 MiB. Houve crescimento
residual de 0,680 MiB, cuja origem não foi isolada. Os 57 testes passaram novamente.
Consulte o [relatório com medições, tempos e limitações](docs/validacao_memory_windows.md)
e as cópias revisadas dos dados em `experimentos/resultados/publicados`.

Na etapa I/O-bound, 101 testes passaram: 22 CPU-bound, 35 Memory-bound e
44 I/O-bound, no Windows com Python 3.14.3. Os novos testes usam pastas isoladas
do pytest em `.temp` e volumes pequenos; não exercitam os máximos com carga de
estresse. Cobrem arquivos reais, escrita/leitura em blocos, JSON, parâmetros,
conteúdo corrompido/truncado, falhas de criação/escrita/leitura/sincronização,
limpeza, preservação de arquivos preexistentes e nomes exclusivos concorrentes.
Também verificam `fsync` habilitado/desabilitado, limites e diretório configurável.
Os hashes das duas aplicações anteriores permaneceram idênticos.
Apenas o aviso conhecido do Starlette sobre HTTPX foi emitido.

## Geração de carga CPU-bound com Locust no Windows

O gerador é separado das APIs e deve executar no Windows contra a VM.
Instale a dependência opcional somente no ambiente virtual local. A versão
do Locust está fixada em `requirements-carga.txt`; ela não precisa ser instalada
no Ubuntu. A preparação foi validada com Python 3.14.3 e Locust 2.46.7.

```powershell
Set-Location D:\atividade-2-poi
New-Item -ItemType Directory -Path .temp -Force | Out-Null
$env:TEMP = 'D:\atividade-2-poi\.temp'
$env:TMP = $env:TEMP
```

Para instalar e conferir, use os comandos abaixo (não há instalação global):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-carga.txt --no-cache-dir
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m locust --version
```

O script `scripts/carga/locustfile.py` contém apenas uma tarefa: `GET /primos`.
`--limite` é fixo por execução (padrão 100000); mantenha exatamente o mesmo
valor em todos os cenários comparados e confirme o teto `CPU_LIMITE_MAX` da VM.
Não há cálculo de primos no gerador. HTTP diferente de 200, JSON inválido ou
resposta incompatível são registrados como falha; a validação não recalcula
a quantidade de primos. O timeout HTTP é 30 s e também pode influenciar falhas
sob saturação: registre e mantenha esse valor ao comparar execuções.

A política é de **modelo fechado**: cada usuário mantém no máximo uma
requisição pendente e espera `--espera` segundos fixos após a tarefa (padrão 1 s).
O valor 0 remove essa pausa e deve ser calibrado antes de uso. Essa espera está
somente no cliente Locust. A aplicação mantém seu processamento real de CPU.
`--taxa` é a taxa de inicialização de usuários/s, não uma taxa de chegada HTTP
independente. A vazão resulta da concorrência, do tempo de resposta e da espera.
Não há seleção aleatória de tarefas ou entradas: parâmetros são reproduzíveis,
mas agendamento, rede e estado da VM impedem tempos idênticos.

Os cenários planejados são:

| Cenário | vCPUs | RAM | Workers Uvicorn |
|---|---:|---:|---:|
| C1 | 1 | 1 GiB | 1 |
| C2 | 1 | 2 GiB | 1 |
| C3 | 2 | 1 GiB | 2 |
| C4 | 2 | 2 GiB | 2 |

O gerador **não altera nem verifica automaticamente** o provisionamento.
Confirme a configuração no VirtualBox e na VM antes de atribuir um cenário.
Na VM, use `python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001
--workers 1` em C1/C2 e `--workers 2` em C3/C4, sem `--reload`.

O executor realiza apenas uma combinação cenário/demanda/repetição por chamada,
sem percorrer automaticamente os níveis preliminares 1, 5, 10, 20 e 40.
Ele primeiro executa aquecimento e depois medição em dois processos Locust
sequenciais. A VM permanece ligada e aquecida, mas as conexões HTTP são recriadas.
Os CSV de aquecimento ficam separados e não devem entrar nas médias finais.

As durações são segundos contados desde o início de cada fase e **incluem a
rampa de usuários**. Ambas devem exceder `usuarios/taxa`; escolha períodos
de regime estável bem maiores que a rampa para os experimentos definitivos.
`--reset-stats` reinicia os acumulados ao concluir a inicialização dos usuários
em cada fase. Isso não elimina linhas anteriores já escritas no CSV histórico:
descarte a rampa ao analisar séries temporais (confira `User Count` e o console).
Requisições que cruzam a fronteira podem ser contabilizadas depois do reset.
O encerramento permite até 35 s para tarefas pendentes; pode ultrapassar a
duração nominal e influenciar os acumulados. O tempo de parede efetivo de cada
processo é registrado. Esses limites impedem tratar o resumo como uma janela
estritamente recortada; defina a janela de análise antes da coleta definitiva.

Para preparar um plano **sem enviar HTTP**, use uma repetição reservada:

```powershell
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --cenario C1 --usuarios 1 --taxa 1 --duracao 15 --aquecimento 5 --limite 100000 --espera 1 --repeticao 99 --somente-preparar
```

Exemplo de **piloto de baixa intensidade**, para executar posteriormente após
confirmar a disponibilidade da VM (não foi executado na preparação):

```powershell
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --url http://127.0.0.1:8001 --cenario C1 --usuarios 1 --taxa 1 --duracao 15 --aquecimento 5 --limite 100000 --espera 1 --repeticao 1
```

Cada chamada cria `experimentos/resultados/carga/C1/usuarios_01/repeticao_01/`.
A pasta não pode existir previamente: nenhuma execução sobrescreve resultados
ou planos. Use outro número para uma nova repetição. `parametros.json` registra
URL, limite, usuários, espera, taxa, duração, aquecimento, cenário planejado,
repetição, versões Python/Locust, comandos, horários UTC, tempos e códigos de
saída. As fases geram `aquecimento_*` e `medicao_*`:

- `*_stats.csv`: contagem de requisições/falhas, vazão, tempos médios/mínimos/
  máximos e percentis de latência; sucessos = requisições menos falhas.
- `*_stats_history.csv`: evolução periódica da vazão, percentis e usuários.
- `*_failures.csv` e `*_exceptions.csv` (quando gerado): detalhes dos problemas.
- `*_console.txt`: saída do Locust para auditoria.

CSV contém agregados e percentis aproximados em milissegundos, não os tempos
individuais de todas as requisições. Falhas no aquecimento interrompem o executor
antes da medição. Registros interrompidos ou com falhas devem ser examinados,
não incorporados silenciosamente às médias. Para execução direta sem interface:

```powershell
.\.venv\Scripts\python.exe -m locust -f scripts/carga/locustfile.py --headless --host http://127.0.0.1:8001 --users 1 --spawn-rate 1 --run-time 15s --limite 100000 --espera 1 --csv .temp/piloto --csv-full-history
```

A execução direta é útil para diagnóstico, mas não registra cenário/repetição
nem separa aquecimento; prefira o executor para experimentos. Verifique que
não existem configurações `locust.conf` ou variáveis `LOCUST_*` inesperadas.
Antes dos ensaios definitivos, calibre a demanda gradualmente, mantenha o limite
e a espera constantes, confirme os workers e recursos efetivos e monitore CPU,
RAM e swap da VM e do Windows. Registre versões do servidor e gerador (por
exemplo `pip freeze`), modo de rede do VirtualBox, intervalo entre execuções e
processos concorrentes. Evite que o gerador ou outras atividades no host se
tornem o gargalo; planeje aquecimento, duração estável e repetições comparáveis.
Revise os novos resultados antes de publicá-los: URLs e mensagens podem conter
informações locais. Não houve execução de carga contra a VM nesta preparação.

Os testes do gerador usam respostas simuladas e processos isolados, sem tráfego
para a VM. Sem a dependência opcional instalada, somente o teste que carrega
Locust é omitido; instale `requirements-carga.txt` para validar toda a suíte.
Na preparação, 115 testes passaram (101 anteriores e 14 novos), sem geração
de carga. Houve o aviso conhecido de descontinuação do HTTPX no Starlette e
um aviso de gravação do cache local do pytest; ambos sem falhas.
Execute a suíte com temporários em D: e uma pasta inédita para preservar
temporários anteriores:

```powershell
$pastaTestes = 'D:\atividade-2-poi\.temp\pytest_carga_' + [guid]::NewGuid().ToString('N')
.\.venv\Scripts\python.exe -m pytest -q --basetemp=$pastaTestes
```

Referências: [configuração e exportação CSV do Locust](https://docs.locust.io/en/stable/configuration.html)
e [tarefas e política de espera](https://docs.locust.io/en/stable/writing-a-locustfile.html).

## Versionamento e publicação

Versione código, testes, scripts, documentação e as cópias revisadas dos resultados
em `experimentos/resultados/publicados`. Os JSON/TXT originais na raiz de
`experimentos/resultados` permanecem locais e ignorados; as cópias públicas
preservam as medições e normalizam os caminhos. Consulte o
[critério de publicação dos resultados](experimentos/resultados/README.md).

O `.gitignore` exclui ambientes virtuais, temporários, caches, logs, arquivos
de configuração local e os resultados originais. Não inclua `.venv` ou `.temp`
com `git add -f`. O arquivo `.gitattributes` padroniza o texto em LF para os
formatos usados pelo projeto, mantendo compatibilidade entre Windows e Ubuntu.

O repositório local foi inicializado com branch `main`. A organização dos commits
e os comandos para conectar um repositório remoto vazio estão no
[guia de preparação do Git](docs/preparacao_repositorio.md). A publicação remota
deve ocorrer somente após autorização e definição da URL da organização.

## Execução futura no Ubuntu Server

Crie um novo `.venv` dentro da VM; ambientes virtuais do Windows não são portáveis
para Linux. Se `venv` ou pip estiverem ausentes, será necessário instalar os
pacotes do sistema correspondentes (`python3-venv` e `python3-pip`) com autorização
do administrador da VM.

O endereço `0.0.0.0` permite receber conexões pelas interfaces da VM. Para acesso
do host, configure uma rede adequada no VirtualBox (por exemplo, host-only ou
redirecionamento de porta em NAT) e permita as portas 8001, 8002 e 8003 no firewall, se ativo.
Use o IP da VM ou a porta encaminhada no lugar de `localhost` no host.

Registre a versão do Python, as dependências efetivamente instaladas, o número de
vCPUs, os trabalhadores, o limite e as condições de carga para comparar medições.
Para registrar versões, use `python -m pip freeze`. Os intervalos em
`requirements.txt` permitem atualizações; use as mesmas versões nos experimentos
que forem comparados.

## Estrutura

```text
apps/
  cpu_bound/main.py
  memory_bound/.gitkeep
  memory_bound/main.py
  io_bound/.gitkeep
  io_bound/main.py
tests/test_cpu.py
tests/test_memory.py
tests/test_io.py
tests/test_carga.py
scripts/
  carga/.gitkeep
  carga/locustfile.py
  carga/executar_locust.py
  monitoramento/.gitkeep
  monitoramento/verificar_memoria_windows.py
  monitoramento/verificar_io_windows.py
experimentos/
  resultados/.gitkeep
  resultados/README.md
  resultados/publicados/  # JSON/TXT revisados dos experimentos locais
  graficos/.gitkeep
docs/.gitkeep
docs/validacao_memory_windows.md
docs/validacao_io_windows.md
docs/preparacao_repositorio.md
requirements.txt
requirements-carga.txt
.gitignore
.gitattributes
README.md
```
