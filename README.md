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

Cada chamada CPU cria `experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/`.
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

Os CSV nativos Locust contêm agregados e percentis aproximados em milissegundos.
O executor também gera `medicao_latencias.csv` com tempos individuais da medição.
Falhas no aquecimento interrompem o executor
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

## Monitoramento de CPU e memória dentro da VM Linux

`scripts/monitoramento/monitorar_linux.py` coleta métricas da VM e da árvore
de um PID informado. Execute-o **dentro do Ubuntu**, enquanto Locust executa
no Windows. Não modifica o servidor, seus workers ou o provisionamento.
Não identifica o serviço somente pelo nome `uvicorn`: o operador deve informar
o PID principal correto. A árvore inclui o principal, workers e eventuais
auxiliares (por exemplo, resource tracker); sua contagem não é necessariamente
igual à quantidade de workers. Descendentes independentes desse PID não são
monitorados. Evite usar um shell ou supervisor genérico que tenha outros serviços
como PID principal. A identidade é o par PID/data de criação, para distinguir
reutilização de PID e substituição de workers.

Instale a dependência separada no ambiente virtual Ubuntu do projeto:

```bash
cd /caminho/atividade-2-poi
source .venv/bin/activate
python -m pip install -r requirements-monitoramento.txt
python -m pip check
```

O arquivo fixa psutil 7.2.2. Nenhuma dependência de monitoramento foi acrescentada
a `requirements.txt`. Use o mesmo usuário do servidor para ler seus processos.
USS/PSS podem requerer permissões adicionais; ausência dessas métricas não
justifica executar indiscriminadamente como root.

Se o servidor já estiver ativo, confira sua árvore com:

```bash
ps -eo pid,ppid,args --forest
```

Localize `python -m uvicorn apps.cpu_bound.main:app` e escolha o principal,
não um worker isolado. Confira PID e PPID; não use automaticamente todos os
resultados de uma busca por `uvicorn`. Para uma futura inicialização controlada
em C1/C2, em um terminal que permanecerá aberto:

```bash
python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 1 &
servidor_pid=$!
printf 'PID principal: %s\n' "$servidor_pid"
```

Não inicie uma segunda instância se a porta já estiver ocupada. Em C3/C4 use
`--workers 2`, sem `--reload`. Transcreva o PID para outro terminal Ubuntu e
inicie a coleta **antes do aquecimento do Locust**. Exemplo, substituindo 1234
pelo PID real:

```bash
python scripts/monitoramento/monitorar_linux.py --pid 1234 --cenario C1 --usuarios 1 --repeticao 1 --intervalo 1 --duracao 120 --resultados experimentos/resultados/carga --condicoes 'VirtualBox NAT; CPU_LIMITE_MAX=1000000; limite Locust=100000; espera=1s; workers=1'
```

`--cenario`, `--usuarios` e `--repeticao` seguem os nomes do executor Locust.
`--duracao` é opcional; sem ela, a coleta segue até Ctrl+C. A duração deve ser
maior que o intervalo. `--memoria-detalhada` habilita USS/PSS, desativados por
padrão para reduzir o custo de leitura. `--condicoes` registra notas sobre a
configuração efetiva, rede, workers, limite, espera e demais condições;
não informe credenciais ou dados pessoais. Os recursos planejados do cenário
ficam nos metadados, junto com CPUs lógicas e RAM total observadas; confirme
manualmente se a configuração efetiva corresponde ao cenário.

Saída CPU nova: `experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/monitoramento_linux/`.
Essa subpasta pode coexistir com os arquivos Locust da mesma repetição, mas
uma coleta preexistente nunca é sobrescrita. Para nova coleta, escolha outra
repetição ou outra raiz de resultados. Não aponte o executor Locust no Windows
para uma pasta de repetição já preenchida: execute em raízes locais separadas
e posteriormente reúna os CSV Linux na subpasta `monitoramento_linux`.

São gerados `sistema.csv`, `processos.csv` e `metadados.json`, em UTF-8.
Ctrl+C fecha os CSV e registra o encerramento, sem encerrar Uvicorn. O término
da duração e o desaparecimento do principal também finalizam a coleta.
Erros de saída ou de enumeração da árvore interrompem e são registrados quando
o diretório permanece gravável. Falhas de leitura de um descendente são
registradas em `erro`; não viram zeros inventados. Confira após a execução:

```bash
head -n 3 experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/monitoramento_linux/sistema.csv
wc -l experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/monitoramento_linux/processos.csv
cat experimentos/resultados/carga/cpu/C1/usuarios_01/repeticao_01/monitoramento_linux/metadados.json
```

Interpretação das métricas:

| Coluna/métrica | Cálculo e significado |
|---|---|
| `utc`, `tempo_relativo_s` | Horário ISO 8601 UTC no início da amostra; segundos monotônicos desde o início da coleta. O monotônico não compara relógios de máquinas diferentes. |
| `intervalo_real_s` | Tempo entre inícios das amostras; atrasos não são substituídos pelo intervalo configurado. |
| `cpu_sistema_capacidade_pct` | `psutil.cpu_percent(interval=None)`: utilização agregada da VM entre chamadas, de 0 a 100% da capacidade de todas as CPUs lógicas. Inclui monitor, servidor e demais atividades do sistema. |
| `cpu_uma_cpu_pct` | `100 × delta(user + system) / delta(monotônico)` de cada processo. 100% significa uma CPU lógica ocupada; pode exceder 100% em processo com várias threads. Não inclui tempos acumulados dos filhos. |
| `cpu_intervalo_real_s` | Denominador efetivamente usado para CPU de cada processo, entre suas leituras. |
| `cpu_capacidade_vm_pct` | Percentual anterior dividido pelo número de CPUs lógicas observado no início. Em 2 vCPUs, 100% de uma CPU corresponde a 50% da VM. |
| `cpu_soma_uma_cpu_pct`, `cpu_soma_capacidade_vm_pct` | Soma dos percentuais dos processos enumerados, nas duas escalas. Só preenchida quando todos têm CPU válida; confira `cpu_processos_completa`. |
| `ram_total_bytes`, `ram_disponivel_bytes` | RAM total e estimativa disponível para novas alocações sem swap, por `psutil.virtual_memory()`. Disponível inclui memória recuperável; não é apenas RAM livre. |
| `ram_usada_psutil_bytes` | Campo `used` da API, conforme a definição Linux da versão instalada; não presuma que seja total menos disponível. |
| `ram_nao_disponivel_bytes`, `ram_percent_psutil` | Total menos disponível; o percentual da API corresponde a `100 × (total − disponível) / total`. |
| `rss_bytes`, `vms_bytes` | Memória residente e espaço de endereçamento virtual por processo. VMS não representa RAM física consumida. |
| `rss_soma_bytes` | **Soma de RSS**, não memória privada: páginas compartilhadas podem ser contadas várias vezes. |
| `uss_bytes`, `pss_bytes` | Opcionais: USS representa páginas exclusivas; PSS reparte páginas compartilhadas proporcionalmente entre processos que as mapeiam. São leituras mais custosas, dependentes de suporte/permissões. |
| `uss_soma_bytes`, `pss_soma_bytes` | Somas somente quando disponíveis em todos os processos da amostra. USS exclui compartilhamento; PSS considera a partilha, inclusive com processos fora da árvore. |
| `processos_adicionados`, `processos_removidos` | Listas JSON de pares PID/data de criação comparados com a amostra anterior. Na primeira amostra todos são novos; perdas de acesso também podem afetar a identificação. |

Campos indisponíveis são células vazias, não zero. A primeira observação de
cada processo serve de referência para CPU e fica sem percentual; a primeira
medição válida aparece na observação seguinte. A CPU do sistema é inicializada
antes da coleta para descartar o primeiro retorno inválido da API. Os CSV não
são uma fotografia atômica: processos e sistema são lidos sequencialmente.
Amostragem ocorre aproximadamente a cada segundo; se houver atraso, não cria
rajadas para recuperar amostras perdidas. O período menor que um intervalo no
fim da duração não gera uma amostra extra. Não altere vCPUs durante a coleta.

Workers que surgem e desaparecem entre amostras podem não ser observados.
CPU executada após a última leitura de um processo encerrado não é recuperada.
Se o principal morrer, a coleta para; não segue workers órfãos nem um novo
servidor em PID reutilizado. O monitor também consome recursos, especialmente
com USS/PSS; mantenha método e intervalo iguais entre cenários e observe seu
impacto durante o piloto. Não há coleta de swap ou I/O nesta versão.

Relacione Linux e Locust por cenário/demanda/repetição e horários UTC dos
metadados. Confira a sincronização dos relógios Windows/Ubuntu antes do teste;
diferenças de relógio afetam alinhamento. Os metadados Locust identificam início
e fim de aquecimento e medição, incluindo rampa e encerramento. Recorte a mesma
janela estável dos CSV históricos e do monitor; não misture repouso, aquecimento
ou encerramento com médias definitivas. Tempo monotônico só relaciona amostras
dentro de uma execução. Revise notas e dados antes de publicação.

O funcionamento Linux **ainda precisa ser validado na VM**. Os testes Windows
usam mocks para árvore, métricas, alterações de PID, permissões, arquivos,
duração e interrupção. Após copiar o script para Ubuntu, faça uma coleta curta
sem carga, confira o PID e os CSV, e só então realize um piloto supervisionado.
Nesta etapa, a suíte Windows passou com 134 testes (115 anteriores e 19 novos
de monitoramento), com apenas o aviso conhecido do Starlette sobre HTTPX.
`pip check` confirmou compatibilidade no ambiente virtual local; isso não
substitui a instalação e a verificação no Ubuntu.
Referência das definições e limitações: [documentação oficial do psutil](https://psutil.readthedocs.io/en/latest/).

## Consolidação dos resultados experimentais

`scripts/analise/consolidar_resultados.py` usa somente a biblioteca padrão
Python (3.10 ou posterior). Não executa carga e não altera os arquivos de entrada.
Recebe uma ou mais pastas `C?/usuarios_NN/repeticao_NN` e gera uma linha por
repetição em `consolidado.csv`, além de `resumo.txt`, numa **pasta nova**.
Não combina repetições nem calcula uma média entre cenários automaticamente.
Confira limite, espera, recursos e versões antes de comparar linhas.

Os formatos foram conferidos nos scripts existentes, nos CSV reais do piloto
e na implementação instalada do Locust 2.46.7. As entradas esperadas são:

- `parametros.json`: identificação, parâmetros e fase `medicao` com horários UTC.
- `medicao_stats.csv`: linha `Aggregated`, com `Request Count`, `Failure Count`,
  `Average Response Time`, `95%` e `Requests/s`.
- `medicao_stats_history.csv`: `Timestamp` em segundos Unix UTC, `User Count`,
  `Total Request Count`, `Total Failure Count`, `Total Average Response Time`.
- `medicao_console.txt`: marcadores `Resetting stats` e `--run-time limit reached`.
- `medicao_failures.csv` e `medicao_exceptions.csv`: verificados para diagnóstico;
  contagens vêm do histórico/resumo, sem somar novamente esses registros.
- `monitoramento_linux/metadados.json`, `sistema.csv`, `processos.csv`, nos formatos
  descritos na seção de monitoramento. `--monitoramento` permite informar uma
  pasta Linux externa para uma única repetição, validando sua identificação.

Os arquivos `aquecimento_*` não entram na análise. Campos/arquivos ausentes são
listados em `avisos`; métricas impossíveis ficam vazias, sem substituir por zero.
Identificação inconsistente, repetição duplicada ou reset de contadores dentro
da janela interrompem a consolidação. Se falta `parametros.json` ou a fase de
medição com horários, não é possível atribuir uma janela confiável e a análise
é interrompida. Uma fase com erro ou incompleta é identificada nos avisos.

Para coletas anteriores sem marcos diretos, informe o offset **real** do relógio local
usado no console Windows: `--offset-log-minutos -180` significa UTC-3. Isso
converte timestamps do console; não corrige o relógio da VM. Os marcadores de
reset e início do encerramento delimitam candidatos. A janela efetiva vai do
primeiro ao último snapshot `Aggregated` estritamente dentro desses limites
com o número de usuários solicitado. Uma queda de usuários interrompe esse
segmento; não une períodos de carga separados. São necessários dois snapshots.
As bordas inteiras do histórico reduzem a janela em relação aos marcadores.

Alternativamente, use `--inicio-utc 2026-10-08T16:00:01Z --fim-utc
2026-10-08T16:00:09Z` para declarar limites já verificados pelo operador;
ambos precisam estar dentro da fase de medição. Os snapshots também são
selecionados estritamente dentro desses limites e com a demanda correta.
Sem offset/marcadores nem limites explícitos, o resumo acumulado continua
disponível, mas a janela e suas métricas ficam ausentes: não presume que
início do subprocesso seja início da carga nem usa duração nominal para
inventar o instante exato de encerramento. Coletas com marcos UTC diretos não
dependem do offset do console; as novas latências individuais permitem a janela
completa entre esses marcos, conforme o procedimento para coleta definitiva.

As amostras Linux passam pelo filtro UTC da janela. Para evitar CPU parcialmente
fora da carga, o intervalo inteiro anterior à amostra também precisa caber
na janela (`intervalo_real_s` ou `cpu_intervalo_real_s`). RAM utiliza as mesmas
linhas conservadoramente filtradas. A ferramenta registra número de valores
válidos, média aritmética entre amostras e máximo para cada métrica. Não interpola
lacunas nem pondera médias pelo tempo: atrasos de coleta exigem cuidado.
As médias individuais de processos são médias das linhas por processo, não a
utilização total da aplicação; para comparar a árvore, use as colunas `cpu_arvore_*`
e `rss_soma_*` provenientes de `sistema.csv`. RSS somado mantém a limitação
de compartilhamento; USS/PSS ausentes continuam ausentes.

| Métrica consolidada | Origem e interpretação |
|---|---|
| `latencia_media_snapshot_ms`, `p95_snapshot_ms`, `vazao_snapshot_rps` | Valores exportados em `medicao_stats.csv`, em ms e requisições/s; são acumulados do último CSV disponível, não necessariamente valores finais nem exclusivos da janela recortada. |
| `req_snapshot`, `falhas_snapshot` | Contadores exportados nesse mesmo snapshot. O escritor periódico pode não ter salvo a última requisição; não corrige usando valores inventados. |
| `req_janela`, `falhas_janela`, `sucessos_janela` | Com registro individual completo, conta eventos na janela `(início, fim]`; sucessos = total menos falhas. Nas coletas anteriores, usa diferenças dos contadores do histórico. Conta conclusões, incluindo requisições iniciadas antes da borda inicial. |
| `vazao_calculada_janela_rps` | Requisições concluídas, incluindo falhas, divididas pela duração real da respectiva janela. Não é igual à quantidade de usuários concorrentes. |
| `latencia_media_calculada_janela_ms` | Com eventos completos: média aritmética das latências em ms. Em dados anteriores, opcionalmente com `--latencias-completas`, reconstrói `(media_final × contagem_final − media_inicial × contagem_inicial) / delta_contagem`; só declare se todas as requisições têm duração disponível. |
| `p95_janela_ms` | Com eventos completos: latência ordenada no posto `ceil(0.95*n)` (percentil empírico, sem interpolação). Ausente em dados anteriores. Percentis móveis não podem ser combinados para recuperar p95 da janela. |
| `cpu_vm_pct_*`, `cpu_arvore_capacidade_pct_*` | Percentuais da capacidade total da VM; `*_media`, `*_max`, `*_n` identificam estatística e quantidade de valores. |
| `cpu_arvore_uma_cpu_pct_*` | Escala de uma CPU lógica: pode chegar a aproximadamente 200% em duas vCPUs. |
| `ram_*_bytes_*`, `rss_soma_bytes_*`, `uss_soma_bytes_*`, `pss_soma_bytes_*` | Valores em bytes. Para MiB, divida por 1048576; não confunda memória usada psutil com total menos disponível. |

O resumo registra parâmetros, versões disponíveis e recursos planejados/observados.
Valores `snapshot` são extraídos dos CSV; diferenças de contagem, vazão,
reconstrução de média e estatísticas de recursos são calculados. Não trate os
escopos como idênticos nem compare p95 acumulado com CPU de outra janela sem
explicitar essa limitação. A nova coleta individual permite calcular média e p95
na mesma janela UTC usada para filtrar recursos; consulte o procedimento abaixo.

**Relógios:** confirme externamente a sincronização Windows/Ubuntu. Somente então
use `--relogios-sincronizados`; o argumento registra a confirmação, não executa
uma verificação NTP. Se mediu uma diferença constante, `--correcao-monitor-s`
soma esse valor ao horário Linux (por exemplo, VM atrasada 2 s: valor `2`),
com precedência sobre a sondagem. Sem override, usa automaticamente a
verificação de relógio incorporada em `parametros.json`, se válida e da mesma URL.
O offset é `Linux − Windows`; portanto, `UTC alinhado = UTC Linux − offset`.
Não ajuste pelo pico de CPU. O script detecta possível salto do relógio através
de UTC versus monotônico nos metadados Windows e nas amostras Linux (aviso
quando a diferença/variação excede 1 s). Ausência de sobreposição também gera
aviso, mas pode significar coleta incompleta. Esses arquivos, sozinhos, não
permitem medir uma diferença constante entre máquinas; sem confirmação,
o alinhamento é explicitamente provisório.

Exemplo com os CSV reais presentes localmente (UTC-3 do console deve ser conferido):

```powershell
.\.venv\Scripts\python.exe scripts/analise/consolidar_resultados.py experimentos/resultados/carga/C1/usuarios_01/repeticao_01 experimentos/resultados/carga/C1/usuarios_01/repeticao_02 --offset-log-minutos -180 --saida experimentos/resultados/analise/piloto_C1
```

Na preparação da ferramenta, somente os arquivos Locust dessas duas repetições
estavam disponíveis localmente; os CSV Linux ainda precisam ser copiados da VM.
A ausência gera avisos e células vazias de CPU/RAM, sem invalidar as métricas
Locust que puderem ser extraídas. Após reunir a coleta correspondente, execute
novamente com uma pasta de saída diferente. Não sobrescreva a análise anterior.
`--monitoramento` não deve apontar para uma coleta de outra repetição.

Testes usam dados sintéticos pequenos e não executam carga:

O piloto local foi consolidado em `experimentos/resultados/analise/piloto_C1/`:
cada repetição gerou uma janela de 13 s, com 13 e 12 requisições registradas
nessas janelas e nenhuma falha. CPU/RAM permaneceram indisponíveis, pois a
coleta Linux não estava presente. O offset do console usado foi UTC-3;
a sincronização entre host e VM não foi declarada. Esses resultados parciais
não constituem comparação definitiva entre cenários.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_analise.py -q
```

## Instrumentação opcional para investigar workers, relógios e CPU

As opções abaixo são restritas ao laboratório. A contagem matemática de primos
e os corpos JSON não mudam. O padrão continua sem cabeçalhos de diagnóstico,
com reutilização HTTP e sem contadores brutos de CPU. Memory-bound e I/O-bound
não foram modificadas. Não houve execução de carga nesta preparação.

Na VM, habilite **explicitamente** `CPU_DIAGNOSTICO=1` ao iniciar Uvicorn.
A variável é lida na criação da aplicação: mudar seu valor exige reiniciar
o servidor. Use somente na rede experimental; os cabeçalhos expõem PID e
horários internos, sem autenticação adicional. Confirme que uma instância
anterior não está ocupando a porta antes de usar este exemplo C4:

```bash
cd /caminho/atividade-2-poi
source .venv/bin/activate
CPU_DIAGNOSTICO=1 python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 2 &
servidor_pid=$!
printf 'PID principal: %s\n' "$servidor_pid"
```

Quando habilitado, respostas HTTP incluem `X-Worker-PID`,
`X-Server-Received-UTC` (entrada no middleware) e `X-Server-Sent-UTC` (emissão
do início da resposta). Em `/health`, esses horários permitem sondar relógios
sem executar o cálculo. Em `/primos`, o PID identifica o processo atendente.
Os cabeçalhos também acompanham erros HTTP. Sem a variável, não são adicionados.

Antes da carga, no Windows, faça uma verificação explícita e curta de relógio:

```powershell
.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8001 --amostras 5 --saida .temp/relogio_C4_r91.json
```

Este comando realiza até cinco chamadas `/health`, com conexão fechada após
cada chamada, fora das estatísticas do Locust. O arquivo deve ser novo. O script
registra falhas de rede/cabeçalhos; retorna código 1 se nenhuma sondagem for
válida. Os quatro horários são T1 (cliente envia), T2 (servidor recebe), T3
(servidor emite cabeçalhos), T4 (cliente termina leitura). São timestamps UTC;
o RTT também é medido com relógio monotônico. Um ajuste perceptível do relógio
durante a sondagem ou horários inconsistentes invalidam a amostra.

O offset definido é **servidor menos cliente**. Com atrasos não negativos e
offset aproximadamente constante durante a chamada, o intervalo admissível é
`[T3 − T4, T2 − T1]`. O ponto médio é uma estimativa que assume trânsito
simétrico; metade da faixa expressa a incerteza dessa suposição, não um intervalo
estatístico de confiança. Agendamento e leitura da resposta entram no atraso.
O JSON preserva todas as sondagens e destaca a menor faixa; não ajusta relógios
nem confirma sincronização automaticamente. Repita antes/depois da carga com
arquivos distintos para procurar deriva. RTT baixo não comprova sincronização.

Para alinhar o Linux ao Windows na análise, some o **negativo** do offset
servidor-cliente. Exemplo puramente sintético: offset estimado −3 s significa
VM atrasada; use `--correcao-monitor-s 3`, mantendo explícita a incerteza.
Não use esse exemplo como medição da VM. A decisão de declarar
`--relogios-sincronizados` exige evidência externa e tolerância definida.

Inicie o monitoramento na VM antes do aquecimento. `--diagnostico-cpu` adiciona
`cpu_bruto.jsonl`, sem mudar colunas ou semântica de `sistema.csv`/`processos.csv`:

```bash
python scripts/monitoramento/monitorar_linux.py --pid "$servidor_pid" --cenario C4 --usuarios 2 --repeticao 91 --intervalo 1 --duracao 120 --diagnostico-cpu --resultados experimentos/resultados/carga --condicoes 'C4; 2 workers; CPU_DIAGNOSTICO=1; limite=250000; espera=0; conexoes=fechar'
```

Se usar outro terminal, informe o PID real no lugar da variável. A duração deve
cobrir repouso inicial, aquecimento, medição e encerramento. Os registros brutos
contêm baseline do sistema, linhas `cpu`/`cpuN` de `/proc/stat`, `CLK_TCK`, UTC
e leituras monotônicas antes/depois; por processo, PID/data de criação, PPID,
linha de comando, `cpu_times()` em segundos, instante monotônico e referência
anterior `(user+system, monotônico)`. Falta de acesso à identificação é registrada.
O diagnóstico acrescenta leitura e escrita: use-o de maneira comparável entre
cenários e revise linhas de comando antes de publicar, pois argumentos podem
conter informações locais.

Para conferir a CPU dos processos, use `100 × delta(user+system) / delta(monotônico)`;
não some `children_user`/`children_system`. Divida por CPUs lógicas para obter
capacidade da VM. Para o sistema, os campos Linux de `/proc/stat` são ticks:
`user nice system idle iowait irq softirq steal guest guest_nice`, conforme
suporte do kernel. Na definição psutil, total exclui duplicação de `guest` e
`guest_nice`; ocupado = total − idle − iowait. CPU global é
`100 × delta(ocupado) / delta(total)`. Use deltas consecutivos dos contadores,
considerando valores negativos como problema de contabilização; psutil os
limita a zero internamente. Os snapshots brutos são independentes, próximos
das chamadas psutil, mas não atômicos nem os snapshots internos exatos da API.
Eles permitem confrontar crescimento dos ticks, tempo de parede e tempos dos
processos; não demonstram antecipadamente a causa da discrepância observada.

No Windows, o executor agora aceita `--conexoes reutilizar` (padrão) ou
`--conexoes fechar` (envia `Connection: close`). A segunda opção solicita ao
servidor o encerramento após a resposta, acrescentando estabelecimento de
conexões às latências. Não garante distribuição uniforme, nem um usuário por
worker. Compare ambos os modos com o mesmo limite, demanda, espera e recursos,
em repetições distintas. Não mude o modo durante uma execução.

Exemplo completo para uma futura repetição de diagnóstico, depois de revisar
relógios e iniciar o monitor na VM; **não foi executado nesta preparação**:

```powershell
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --url http://127.0.0.1:8001 --cenario C4 --usuarios 2 --taxa 2 --duracao 40 --aquecimento 10 --limite 250000 --espera 0 --repeticao 91 --conexoes fechar --registrar-worker-pid --verificacao-relogio .temp/relogio_C4_r91.json
```

Use `--somente-preparar` para registrar o plano sem enviar requisições. Não
inicie uma repetição preparada na mesma pasta: escolha um novo número. Para
o modo padrão, omita `--conexoes` ou informe `reutilizar`. A verificação de
relógio é anexada aos metadados para auditoria; o executor preserva horários
originais e o consolidador aplica a correção estimada durante a análise.
Confira URL, idade e condições das sondagens antes de usá-las.

Cada fase gera `aquecimento_instrumentacao.json` ou `medicao_instrumentacao.json`
e o executor também incorpora esses dados em `parametros.json`. Os eventos
registram `fase_inicio_utc`, `usuarios_prontos_utc` (após o reset no runner
local), `encerramento_inicio_utc` e `fase_fim_utc`. A análise prefere os marcos
diretos entre usuários prontos e início do encerramento; limites explícitos
continuam tendo prioridade. Os dados anteriores continuam usando console e
offset declarado. Os horários externos do subprocesso permanecem nos metadados.

Com `--registrar-worker-pid`, contadores em memória registram PID/status HTTP.
`pids_janela` cobre completamentos após usuários prontos e antes do encerramento;
`pids_apos_encerramento` inclui completamentos durante a drenagem. O contador
é reiniciado ao terminar a rampa e salvo somente nos eventos, sem arquivo por
requisição. Cabeçalho ausente/inválido aparece como `ausente_ou_invalido`, sem
inventar PID. Status HTTP 200 não comprova validação JSON bem-sucedida: os
contadores são de respostas HTTP, e falhas de conteúdo continuam no Locust.
Requisições que atravessam uma fronteira temporal são contabilizadas ao completar.
Essa instrumentação foi preparada para Locust local, sem distribuição master/worker.

Os testes usam mocks e respostas locais pequenas, sem carga contra a VM.
A instrumentação mantém a lógica matemática da aplicação. A causa da
incompatibilidade entre CPU global e tempos dos processos no VirtualBox
continua pendente de investigação; a ferramenta mantém as fontes separadas.

## Procedimento para a coleta definitiva

Use os mesmos scripts, versões e opções de diagnóstico em C1–C4. Mantenha
`limite=250000`, `espera=0` e `conexoes=fechar` em todas as repetições comparáveis.
O modelo é fechado: cada usuário espera a resposta antes de iniciar outra
requisição; `--taxa` controla a rampa de usuários, não a taxa de requisições.
Fechar conexões acrescenta esse custo à latência e não garante balanceamento.
Escolha demandas e durações após a calibração; os números abaixo são um exemplo
de procedimento, não um experimento executado automaticamente.

Na VM, confirme CPU/RAM realmente provisionadas e workers. Para C4, em um
terminal dedicado na raiz do projeto:

```bash
source .venv/bin/activate
CPU_DIAGNOSTICO=1 python -m uvicorn apps.cpu_bound.main:app --host 0.0.0.0 --port 8001 --workers 2 &
servidor_pid=$!
python scripts/monitoramento/monitorar_linux.py --pid "$servidor_pid" --cenario C4 --usuarios 2 --repeticao 100 --intervalo 1 --duracao 240 --diagnostico-cpu --resultados experimentos/resultados/carga --condicoes 'C4; 2 vCPUs; 2 GiB RAM; 2 workers; limite=250000; espera=0; conexoes=fechar'
```

C1/C2 utilizam um worker; C3/C4, dois. Não reutilize diretórios de repetições
existentes. Inicie a coleta antes do aquecimento e confira que ela cobre toda a
medição, considerando sondagens, inicialização e drenagem (até 35 s por fase).
Se a preparação demorar, reveja a duração de monitoramento antes da carga.
Não remova o monitoramento anterior para repetir uma coleta.

No Windows, na raiz do projeto, com dependências opcionais já instaladas em
`.venv` (`requirements-carga.txt`; na VM, `requirements-monitoramento.txt`):

```powershell
$env:TEMP='D:\atividade-2-poi\.temp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8001 --amostras 5 --saida .temp/relogio_C4_r100_antes.json
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --url http://127.0.0.1:8001 --cenario C4 --usuarios 2 --taxa 2 --aquecimento 30 --duracao 60 --limite 250000 --espera 0 --conexoes fechar --registrar-worker-pid --verificacao-relogio .temp/relogio_C4_r100_antes.json --limite-latencias 100000 --repeticao 100
.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8001 --amostras 5 --saida .temp/relogio_C4_r100_depois.json
```

Esses comandos enviam requisições: execute-os apenas quando iniciar o
experimento autorizado. Para preparar um plano sem HTTP, use somente o comando
do executor com `--somente-preparar`, sem executar sondagens; ele reserva uma
pasta, portanto use outro número para a futura execução. TEMP/TMP valem apenas
para a sessão atual. Preserve também a sondagem posterior junto da documentação
da execução, em arquivo novo; ela não é incorporada automaticamente. Compare
offsets e suas faixas de incerteza antes/depois: deriva, ajustes de relógio ou
faixas incompatíveis exigem revisão do alinhamento, não uma correção silenciosa.

O executor cria `medicao_latencias.csv`, com `concluida_utc`, `latencia_ms`,
`falha` e `worker_pid`. O registro inicia após a rampa/reset e termina antes da
drenagem. Aquecimento ocorre em outro processo e não gera esse CSV. São escritas
linhas pequenas com buffer, sem manter latências em RAM durante a carga ou fazer
`fsync` por requisição. Há custo de instrumentação no Windows: use a mesma
política em todos os cenários. O limite padrão é 100000 registros; o máximo
configurável é 1000000. O JSON da fase registra contagem, descartes, erros e
completude. Truncamento, duração ausente ou arquivo incompleto impedem publicar
média/p95 individuais como completos. Falhas com duração válida entram nessas
estatísticas; falhas sem duração invalidam a completude.

Copie os arquivos de monitoramento da VM para a pasta da mesma repetição no
Windows, sem substituir arquivos preexistentes. Para consolidar em pasta nova:

```powershell
.\.venv\Scripts\python.exe scripts/analise/consolidar_resultados.py experimentos/resultados/carga/cpu/C4/usuarios_02/repeticao_100 --saida experimentos/resultados/analise/definitivos_C4_r100
```

A análise preserva todos os originais. Para eventos completos usa os marcos UTC
diretos, ou `--inicio-utc`/`--fim-utc` dentro desses marcos; para dados antigos
mantém o recorte por snapshots. Continua exigindo histórico suficiente para
verificar demanda estável. `*_snapshot` permanece acumulado; nas novas coletas,
`req_hist_janela`, `falhas_hist_janela`, `inicio_hist_janela_utc`,
`fim_hist_janela_utc`, `duracao_hist_janela_s`, `vazao_hist_calculada_janela_rps`
e `latencia_media_hist_calculada_ms` identificam o recorte histórico separado.
Não compare percentis Locust arredondados com percentis empíricos como se
usassem o mesmo método. Sem eventos individuais, p95 da janela fica ausente.

O consolidado registra modo de conexão, usuários, limite, espera, rampa,
durações e marcos de fases, recursos/worker planejados e recursos Linux
observados. Provisionamento planejado não comprova configuração efetiva.
Registra também correção, origem, offset, incerteza e idade da sondagem.
Por exemplo, offset `-3.9826785 s` resulta em somar `+3.9826785 s` ao UTC Linux.
A incerteza de comunicação não cobre deriva posterior nem prova sincronização;
amostras próximas das bordas devem ser interpretadas com essa tolerância.

Com `cpu_bruto.jsonl`, confere `100*delta(user+system)/delta(monotônico)` contra
CPU/intervalo dos processos no CSV e sua normalização por CPUs lógicas. Registra
contagem conferida, segundos de CPU acumulados e erro máximo em pontos
percentuais. Não inclui tempos dos filhos. Para o sistema registra deltas de
ticks em segundos e intervalos monotônicos, separadamente. Leituras são
sequenciais e não atômicas. Avisos são emitidos para diferenças acima de 5% na
capacidade bruta esperada, tempo ocupado global menor que o da árvore ou média
global mais de 5 pontos abaixo da árvore. Esses limiares são diagnósticos, não
uma correção nem prova de causa. A CPU global permanece a métrica original
psutil; não é substituída pela CPU dos processos. CSV antigos e contadores
ausentes continuam aceitos, com avisos e campos indisponíveis.

## Experimentos nas três aplicações

O executor aceita `--aplicacao cpu|memoria|io` (padrão `cpu`). Sem `--url`, escolhe
`http://127.0.0.1:8001`, `:8002` ou `:8003`. Novas execuções e monitoramentos usam
`experimentos/resultados/carga/<aplicacao>/<cenario>/usuarios_NN/repeticao_NN/`.
Os caminhos históricos sem aplicação permanecem intactos e são interpretados
como CPU pelo consolidador. A identificação inclui aplicação: é possível consolidar
CPU, memória e I/O com os mesmos cenário/demanda/repetição sem confundi-los.

### Endpoints e configuração real

| Aplicação | GET e parâmetros HTTP | Configuração inicial do servidor |
|---|---|---|
| cpu | `/primos?limite=100000`; 1 até `CPU_LIMITE_MAX` | `CPU_LIMITE_MAX=1000000`; `CPU_DIAGNOSTICO=0` |
| memoria | `/memoria?tamanho_mb=50`; MiB entre os limites | `MEMORY_LIMITE_MIN_MB=1`, `MEMORY_LIMITE_MAX_MB=64`, `MEMORY_MAX_SIMULTANEAS=4`, `MEMORY_RETENCAO_SEGUNDOS=0` |
| io | `/arquivo?tamanho_mb=10&operacoes=1`; MiB 1–32, operações 1–5 com configuração inicial | `IO_TAMANHO_MAX_MB=32`, `IO_OPERACOES_MAX=5`, `IO_MAX_SIMULTANEAS=2`, `IO_FSYNC=0`, `IO_DIRETORIO_TEMP=.temp/io_bound` |

Todas têm `/health`. Retenção é de 0 a 5 segundos, após escrita/verificação da
memória. Memória admite máximo × simultâneas ≤ 256 MiB **por worker**. I/O admite
máximo × simultâneas ≤ 128 MiB por worker e máximo × operações máximas ≤ 160 MiB
escritos por pedido. Esses orçamentos são multiplicados pelo número de workers.
Limites de concorrência podem gerar HTTP 503; devem ser registrados como falhas,
sem ocultá-los por retentativas. A retenção influencia a latência deliberadamente.

`--tamanho-mb` escolhe alocação/arquivo e `--operacoes` só vale para I/O.
`--retencao-segundos` e `--fsync` são **declarações da configuração na VM**:
não são query parameters e não configuram o servidor remoto. Configure suas
variáveis de ambiente antes de iniciar/reiniciar Uvicorn. Para limites diferentes,
`--config-servidor arquivo.json` aceita um objeto com as variáveis do perfil
acima, completa as demais com os padrões e valida os orçamentos antes da carga.
Não aceita chaves desconhecidas. Por exemplo, para I/O:

```json
{"IO_TAMANHO_MAX_MB": 16, "IO_OPERACOES_MAX": 5, "IO_MAX_SIMULTANEAS": 2,
 "IO_FSYNC": 1, "IO_DIRETORIO_TEMP": ".temp/io_experimento"}
```

Esse JSON não altera a VM. Faça os valores coincidirem com o comando real de
inicialização. As declarações completas, parâmetros HTTP efetivos, recursos
planejados, aplicação e opções Locust entram em `parametros.json` e no consolidado;
`configuracao_servidor_verificada=false` explicita a ausência de verificação remota.
`--limite` só é usado no pedido CPU; mantenha-o constante nos ensaios CPU.

### Servidores Ubuntu e diagnóstico opcional

Na raiz do projeto, instale somente no ambiente virtual da VM:

```bash
python3 -m venv .venv  # somente se ainda não houver ambiente Linux
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-monitoramento.txt
```

Escolha **um** dos comandos seguintes para a aplicação estudada, no mesmo
terminal. Exemplo C4 (dois workers; em C1/C2 use um). O ponto de entrada
experimental é uma factory que importa a API existente e envolve somente seu
protocolo HTTP. `POI_DIAGNOSTICO=1` habilita PID e timestamps UTC nas três APIs;
sem essa variável, o diagnóstico é desativado. Não altera cálculos, buffers,
arquivos, lifespan ou corpos JSON. Os módulos originais das APIs continuam válidos.

```bash
POI_APLICACAO=cpu POI_DIAGNOSTICO=1 CPU_LIMITE_MAX=1000000 python -m uvicorn scripts.monitoramento.servidor_experimental:criar_app --factory --host 0.0.0.0 --port 8001 --workers 2 &
servidor_pid=$!
```

```bash
POI_APLICACAO=memoria POI_DIAGNOSTICO=1 MEMORY_LIMITE_MIN_MB=1 MEMORY_LIMITE_MAX_MB=64 MEMORY_MAX_SIMULTANEAS=4 MEMORY_RETENCAO_SEGUNDOS=1 python -m uvicorn scripts.monitoramento.servidor_experimental:criar_app --factory --host 0.0.0.0 --port 8002 --workers 2 &
servidor_pid=$!
```

```bash
POI_APLICACAO=io POI_DIAGNOSTICO=1 IO_TAMANHO_MAX_MB=32 IO_OPERACOES_MAX=5 IO_MAX_SIMULTANEAS=2 IO_FSYNC=1 IO_DIRETORIO_TEMP=.temp/io_experimento python -m uvicorn scripts.monitoramento.servidor_experimental:criar_app --factory --host 0.0.0.0 --port 8003 --workers 2 &
servidor_pid=$!
```

Confira `ps -p "$servidor_pid" -o pid,ppid,args` e os recursos da VM.
O PID principal informado deve pertencer à aplicação escolhida. A seleção
`--aplicacao` organiza arquivos; a árvore continua sendo identificada pelo PID.
Sem o wrapper, memória/I/O **não oferecem** cabeçalhos de worker/relógio;
sondagens falham explicitamente e PID aparece como ausente. Não invente um
offset nesses casos. Em CPU, `CPU_DIAGNOSTICO=1` ainda funciona no módulo original;
o wrapper preserva cabeçalhos existentes, sem duplicá-los.

### Testes locais e monitoramento

Exemplos para execução posterior, no Ubuntu, sem Locust:

```bash
curl -i http://127.0.0.1:8001/health
curl 'http://127.0.0.1:8001/primos?limite=10'
curl 'http://127.0.0.1:8002/memoria?tamanho_mb=1'
curl 'http://127.0.0.1:8003/arquivo?tamanho_mb=1&operacoes=1'
df -h .temp/io_experimento
find .temp/io_experimento -maxdepth 1 -type f -name 'io_bound_*.tmp' -print
```

Use apenas as portas dos serviços ativos. O último comando verifica limpeza,
sem excluir arquivos. Configure encaminhamento NAT das portas necessárias.
Antes de escrever, confira também espaço no host que contém o disco virtual.

Inicie o monitor correspondente antes do aquecimento; escolha um destes:

```bash
python scripts/monitoramento/monitorar_linux.py --aplicacao cpu --pid "$servidor_pid" --cenario C4 --usuarios 2 --repeticao 101 --intervalo 1 --duracao 240 --diagnostico-cpu --condicoes 'CPU; 2 vCPUs; 2 GiB; 2 workers; limite=250000; espera=0; fechar'
python scripts/monitoramento/monitorar_linux.py --aplicacao memoria --pid "$servidor_pid" --cenario C4 --usuarios 2 --repeticao 101 --intervalo 1 --duracao 240 --memoria-detalhada --diagnostico-cpu --condicoes 'RAM; 2 workers; tamanho=10 MiB; retencao=1 s; max_simultaneas=4'
python scripts/monitoramento/monitorar_linux.py --aplicacao io --pid "$servidor_pid" --cenario C4 --usuarios 2 --repeticao 101 --intervalo 1 --duracao 240 --discos --diagnostico-cpu --condicoes 'IO; 2 workers; arquivo=1 MiB; operacoes=1; fsync=1; diretorio=.temp/io_experimento'
```

Ctrl+C encerra o monitor, fecha seus arquivos e preserva Uvicorn.
`--discos` é opcional em qualquer perfil e acrescenta `discos.csv`. Registra por
dispositivo contadores acumulados de bytes lidos/escritos e operações, deltas,
bytes/s e delta de tempo ocupado em ms, quando disponível. Intervalo é o delta
monotônico real entre leituras; a primeira observação não tem delta. Dispositivos
novos, removidos, sem acesso ou com contador reiniciado não recebem valores
inventados. Mantém os CSV de CPU/RAM com a semântica anterior.

São contadores do kernel da **VM inteira**, não contadores do endpoint. Incluem
outros serviços e gravações do próprio monitor. Partições e discos podem contar
a mesma operação: a análise mantém dispositivos separados, sem somá-los. Cache,
filesystem, filas, mesclagem de operações e disco virtual afetam a relação com
bytes HTTP. Esses contadores não comprovam escrita física no disco do Windows.
`flush()` não garante persistência; `fsync()` solicita sincronização ao sistema,
mas não elimina cache de leitura nem garante acesso à mídia física do host.
Contadores ausentes em coletas antigas são tratados como dados indisponíveis.

### Locust Windows, relógios, transferência e análise

Na raiz do projeto:

```powershell
$env:TEMP='D:\atividade-2-poi\.temp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements-carga.txt
```

Faça sondagem na porta da aplicação estudada, depois escolha a respectiva carga:

```powershell
.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8001 --saida .temp/relogio_cpu_101_antes.json
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --aplicacao cpu --cenario C4 --usuarios 2 --taxa 2 --aquecimento 30 --duracao 60 --limite 250000 --espera 0 --conexoes fechar --registrar-worker-pid --verificacao-relogio .temp/relogio_cpu_101_antes.json --repeticao 101

.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8002 --saida .temp/relogio_memoria_101_antes.json
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --aplicacao memoria --cenario C4 --usuarios 2 --taxa 2 --aquecimento 30 --duracao 60 --tamanho-mb 10 --retencao-segundos 1 --espera 0 --conexoes fechar --registrar-worker-pid --verificacao-relogio .temp/relogio_memoria_101_antes.json --repeticao 101

.\.venv\Scripts\python.exe scripts/monitoramento/verificar_relogios.py --url http://127.0.0.1:8003 --saida .temp/relogio_io_101_antes.json
if (Test-Path .temp/config_io_101.json) { throw 'Configuração já existe; confira antes de reutilizar.' }
'{"IO_DIRETORIO_TEMP":".temp/io_experimento","IO_FSYNC":1}' | Out-File .temp/config_io_101.json -Encoding utf8
.\.venv\Scripts\python.exe scripts/carga/executar_locust.py --aplicacao io --cenario C4 --usuarios 2 --taxa 2 --aquecimento 30 --duracao 60 --tamanho-mb 1 --operacoes 1 --fsync 1 --config-servidor .temp/config_io_101.json --espera 1 --conexoes fechar --registrar-worker-pid --verificacao-relogio .temp/relogio_io_101_antes.json --repeticao 101
```

O comando I/O registra o diretório usado no exemplo Ubuntu por meio do JSON.
Não trate a declaração como configuração observada automaticamente.
Faça uma sondagem posterior na mesma URL, com arquivo novo `*_depois.json`,
e compare offsets/incertezas conforme o procedimento definitivo anterior.
Não execute os três blocos simultaneamente. Calibre memória/I/O separadamente;
estes exemplos não autorizam volumes maiores nem definem a demanda final.
O modo CPU existente mantém defaults; os parâmetros calibrados são explícitos.

Transfira somente a pasta de monitoramento correspondente após sua conclusão.
Exemplo OpenSSH no Windows, substituindo usuário/IP e raiz reais (ou configure
porta SSH encaminhada com `scp -P PORTA`). A destino não pode conter uma coleta:

```powershell
$origem='usuario@IP_DA_VM:/caminho/do/projeto/experimentos/resultados/carga/io/C4/usuarios_02/repeticao_101/monitoramento_linux'
$destino='experimentos/resultados/carga/io/C4/usuarios_02/repeticao_101'
if (Test-Path "$destino/monitoramento_linux") { throw 'Coleta já existe; não sobrescrever.' }
scp -r $origem $destino
.\.venv\Scripts\python.exe scripts/analise/consolidar_resultados.py experimentos/resultados/carga/io/C4/usuarios_02/repeticao_101 --saida experimentos/resultados/analise/io_C4_r101
```

Troque `io` por `cpu` ou `memoria` para as demais coletas. O destino do Locust
deve existir e conter a mesma identificação experimental antes da transferência.
O consolidador verifica aplicação/cenário/demanda/repetição dos metadados Linux.
O cálculo de latências, correção estimada de relógio, filtro de intervalos e
avisos sobre CPU global continuam iguais. `discos_janela` contém JSON com
estatísticas por dispositivo: somas de deltas nos intervalos inteiramente
contidos na janela, médias/máximos de bytes/s e quantidades válidas. Lacunas ou
resets deixam totais incompletos indisponíveis, sem extrapolar à janela inteira.

Para validar ferramentas localmente, sem VM:

```powershell
$pastaTestes=Join-Path $env:TEMP ('pytest_perfis_'+[guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp $pastaTestes
```

As validações Linux/disco usam mocks no Windows; não substituem uma validação
experimental dentro da VM. Não há ajuste remoto de retenção/fsync, comprovação
automática de provisionamento, medição física do host ou atribuição exclusiva de
I/O à API. Nenhuma dependência nova foi adicionada nesta extensão.

## Orquestrador dos experimentos definitivos

`scripts/experimentacao/orquestrar.py` funciona no Windows e reutiliza executor,
sondagens, monitor e consolidador. **O padrão é planejamento**, sem SSH, HTTP ou
carga. `--validar-ambiente` faz auditoria SSH e GET `/health`, mas não sondagens
de relógio nem carga. Somente `--executar` permite iniciar as coletas. Nenhuma
execução remota foi realizada durante a implementação do orquestrador.

O alvo padrão é a VM declarada `POI-Ubuntu-Server`, SSH
`osboxes@127.0.0.1:2222`, projeto `/home/osboxes/atividade-2-poi`. O nome da VM
é uma declaração do operador; a auditoria observa recursos via SSH, sem controlar
VirtualBox. Não altera vCPUs, RAM, workers ou servidores. Selecione e confirme
manualmente o cenário antes de executar. Execução/validação exigem um único cenário.

### Matriz e identificação

| Aplicação | Parâmetros fixos | Usuários |
|---|---|---|
| cpu | limite 250000 | 1, 2, 5, 10 |
| memoria | 50 MiB; retenção efetiva 1 s | 1, 2, 3 |
| io | 10 MiB; 1 operação; `IO_FSYNC=1` efetivo | 1, 2 |

Cada combinação tem três repetições lógicas. Aquecimento 30 s, medição configurada
60 s (ambas incluem rampa), espera zero, conexões fechadas e taxa de criação igual
ao número de usuários. CPU recebe diagnóstico bruto; memória, diagnóstico bruto
e USS/PSS; I/O, ambos mais contadores de disco. Monitoramento a cada 1 s, por
200 s por padrão. A duração mínima permitida é 180 s, considerando drenagens e
margem; coletas que não cobrem a carga após alinhamento UTC são recusadas.

A inspeção local encontrou formatos históricos `carga/C1/...` e `carga/C4/...`,
além de `carga/memoria/...` e `carga/io/...`, com repetições exploratórias até R107.
Nenhuma foi movida ou alterada. A reserva definitiva usa:

`R = base + 10 × (tentativa − 1) + repetição lógica`.

Com base 1000: primeira tentativa R1001–R1003; segunda R1011–R1013.
`--base-repeticao` aceita múltiplos de 1000 a partir de 1000; `--tentativa` vai
de 1 a 99. As pastas seguem o padrão existente
`carga/<aplicacao>/<cenario>/usuarios_NN/repeticao_NN/`. A existência local/remota
impede reutilização, independentemente do ID de campanha. A reserva não substitui
a conferência de colisões, que é feita antes de criar cada coleta.

`--id-execucao` identifica a campanha e seus manifestos em
`experimentos/resultados/orquestracao/<id>/`. `indice.json` reúne estados
planejada, em andamento, concluída, falha e interrompida. O arquivo
`orquestracao/indice_geral.json` reúne os índices das campanhas. Cada combinação tem
um `manifesto.json`, configuração verificada, sondagens antes/depois, console
Locust e análise. O manifesto registra comandos, payloads SSH sem credenciais,
horários, status, caminhos, configuração auditada, avisos e hashes dos artefatos.

### Preparação manual da VM

Disponibilize os scripts atuais no mesmo projeto da VM antes de iniciar servidores.
O auxiliar SSH precisa de `psutil`, já previsto em `requirements-monitoramento.txt`.
Não há dependências novas. Para copiar apenas o auxiliar, posteriormente:

```powershell
ssh -p 2222 osboxes@127.0.0.1 'mkdir -p /home/osboxes/atividade-2-poi/scripts/experimentacao'
scp -P 2222 scripts/experimentacao/agente_linux.py osboxes@127.0.0.1:/home/osboxes/atividade-2-poi/scripts/experimentacao/agente_linux.py
```

Confirme também que `perfis.py`, o monitor com `--aplicacao`/`--discos` e a factory
experimental estão atualizados na VM. Use os comandos de inicialização das três
APIs na seção anterior, com workers do cenário. CPU deve aceitar limite 250000,
memória usar `MEMORY_RETENCAO_SEGUNDOS=1`, I/O usar `IO_FSYNC=1`, e todas oferecer
cabeçalhos experimentais. Escolha diretório I/O dedicado e confira espaço livre.

O helper associa portas a árvores Uvicorn, distingue o principal dos workers
`multiprocessing`, lê somente variáveis relevantes dos processos e compara
configurações entre gerenciador e workers. Padrões são auditados por AST em
`os.getenv`, com hash do código. Se o código foi modificado depois da criação
dos processos, a auditoria exige reinício. Não importa nem executa as APIs para
descobrir padrões. Ausência de acesso a PID, ambiente, socket ou identificação
segura interrompe a validação. Processos de servidor nunca são encerrados.

MemTotal é comparado com a RAM planejada na faixa de 85%–105%, para comportar
reserva do kernel; o valor real é salvo. CPUs lógicas e número de workers precisam
coincidir exatamente. O helper verifica escrita em resultados e no diretório I/O;
para I/O exige pelo menos 256 MiB livres. A sonda de escrita é exclusiva e somente
esse arquivo recém-criado é removido. Nenhum resultado preexistente é excluído.

### Planejar, validar C4 e executar uma repetição

No Windows, na raiz do projeto, com `.venv`, Locust e OpenSSH disponíveis:

```powershell
# Sem rede ou carga; reserve um ID novo.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --planejar --id-execucao definitivos_C4 --cenario C4

# Audita os três servidores C4; usa a mesma campanha sem sobrescrever validações.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --validar-ambiente --id-execucao definitivos_C4 --retomar --cenario C4

# SOMENTE quando autorizado: uma combinação CPU, repetição lógica 1 (R1001).
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --id-execucao definitivos_C4 --retomar --cenario C4 --confirmar-provisionamento C4 --aplicacao cpu --usuarios 1 --repeticao 1
```

Para planejar toda a matriz, omita os filtros de cenário/aplicação/usuários/repetição:
são 108 execuções planejadas, sem dispará-las. Para validar apenas o servidor CPU,
acrescente `--aplicacao cpu`; os demais não precisam estar ligados. Para uma única
coleta de memória, escolha `--aplicacao memoria --usuarios 1 --repeticao 1`;
para I/O, `--aplicacao io --usuarios 1 --repeticao 1`. Retenção/fsync não são
alterados remotamente: valores incompatíveis bloqueiam a execução.

Na execução, o fluxo é: auditoria → relógio antes → monitor remoto → comprovação
de prontidão (processo vivo, metadados executando e primeira linha CSV) → Locust
→ relógio imediatamente depois → término do monitor → SCP para destino novo
→ conferência de identidades/cobertura/relógios → consolidação. Não espera um
atraso fixo para presumir que o monitor está pronto. Polling padrão de 1 s é
apenas consulta de estado. Cada operação tem limites configuráveis:
`--timeout-ssh`, `--timeout-locust`, `--timeout-prontidao`,
`--timeout-transferencia`, `--duracao-monitor` e `--intervalo-consulta`.

As sondagens ficam também na pasta da repetição. A configuração efetiva auditada
é passada ao executor por JSON; somente os metadados recém-criados desta tentativa
são enriquecidos com a verificação e a sondagem posterior. Os horários originais
continuam intactos. Faixas de offset antes/depois sem sobreposição impedem tratar
o resultado como definitivo; isso aponta incerteza/deriva, sem inventar correção.
O consolidado precisa conter latências individuais e recursos válidos. Avisos
de CPU global inconsistente são preservados no resumo e no manifesto.

### Interrupções, retomada e isolamento

Falha inesperada, código Locust não zero, timeout ou Ctrl+C interrompe a sequência.
Somente a árvore local criada pelo orquestrador e seu monitor remoto podem receber
sinais. O controle remoto comprova PID, instante de criação e comando; se houver
dúvida, recusa encerramento. Nunca sinaliza o PID principal das APIs.

Há reserva exclusiva local em `.temp/poi_orquestrador.lock` e remota em
`.temp/poi_experimentos.lock`. Também bloqueia geradores Locust detectados no
host e monitores ativos na VM. A reserva dura até concluir a execução sequencial;
nenhum próximo teste começa enquanto o monitor anterior estiver ativo. Somente
as reservas criadas pelo próprio controlador são removidas automaticamente.

Para retomar a mesma campanha, use `--retomar`. Resultados concluídos só são
pulados após conferir hashes dos artefatos. Planos ainda não iniciados podem
prosseguir. Tentativas em andamento, falhas ou interrompidas não são reaproveitadas:
escolha identificação nova por `--tentativa 2`, preservando R1001 e criando R1011:

```powershell
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --planejar --id-execucao definitivos_C4 --retomar --cenario C4 --aplicacao cpu --usuarios 1 --repeticao 1 --tentativa 2
```

A execução dessa nova tentativa requer novamente `--executar` e confirmação do
provisionamento. Não há retomada de carga pela metade nem cópia sobre arquivos
parciais. O índice mantém as tentativas anteriores separadas.

Limitações: configure manualmente VirtualBox, servidores, encaminhamento de portas,
autenticação SSH por chave/agente e confiança no host SSH. Não salva senhas nem
desativa validação de host. O código suporta Uvicorn padrão com workers
`multiprocessing`; launchers diferentes, acesso negado ao `/proc` ou código
modificado exigem intervenção. A auditoria de arquivos/ambiente não inspeciona
objetos Python na memória: preserve arquivos e reinicie após atualizações.
Tráfego de outros computadores não pode ser excluído automaticamente: reserve
a VM para o experimento. Contadores de disco são da VM inteira e não I/O exclusivo
da API ou escrita física do host.

Se SSH cair durante lançamento ou encerramento, o manifesto salva o token e o
aviso; uma reserva pode permanecer. Inspecione o processo e o journal remoto
`.temp/orquestracao/<token>/controle.json` antes de qualquer remoção manual.
Não considere ausência de resposta SSH prova de que o processo terminou. Arquivos
parciais permanecem para diagnóstico. TEMP/TMP são direcionados para `.temp` no
ambiente dos processos Locust criados, sem configurações permanentes do Windows.

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
tests/test_monitoramento.py
tests/test_analise.py
tests/test_relogios.py
tests/test_latencias.py
tests/test_experimentacao.py
tests/test_orquestrador.py
scripts/
  experimentacao/__init__.py
  experimentacao/orquestrar.py
  experimentacao/agente_linux.py
  analise/consolidar_resultados.py
  carga/.gitkeep
  carga/locustfile.py
  carga/executar_locust.py
  carga/latencias.py
  carga/perfis.py
  monitoramento/.gitkeep
  monitoramento/verificar_memoria_windows.py
  monitoramento/verificar_io_windows.py
  monitoramento/monitorar_linux.py
  monitoramento/verificar_relogios.py
  monitoramento/servidor_experimental.py
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
requirements-monitoramento.txt
.gitignore
.gitattributes
README.md
```
