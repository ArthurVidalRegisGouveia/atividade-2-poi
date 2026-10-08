# Diagnóstico C4 / I/O / dois usuários / R2002

Inspeção sem carga, sondagens ou alterações nos resultados históricos.

## Evidências e limites da atribuição causal

Os comandos de aquecimento e medição em `parametros.json` contêm `--users 2`
e `--spawn-rate 2.0`. O orquestrador também transmite esses valores corretamente.
As fases usam processos Python separados. Não existe argumento zero nesses comandos.

No aquecimento, o console registra dois usuários à taxa 2 e depois uma redução
para zero à taxa 100, imediatamente antes do encerramento. Na medição registra
zero usuários à taxa 100. O histórico confirma zero usuários e requisições.

O código da versão instalada em `.venv/Lib/site-packages/locust/main.py` inicia
um leitor de teclado mesmo com `--headless`. Os atalhos `s` e `S` diminuem usuários
usando `runner.start(..., 100)`. No Windows, `input_events.py` usa
`PeekConsoleInput`, sem consumir esses eventos, e cada processo reinicia o índice
de leitura. Os dois níveis de subprocessos do projeto herdavam o console.
Essa entrada interativa é uma interferência real, demonstrada no código, e explica
a assinatura de taxa 100 nos logs. Não foi capturado o evento de teclado original:
a tecla exata e o instante de sua entrada permanecem não verificáveis. Não se
atribui a falha a parâmetros zero enviados pelo orquestrador nem à API I/O.

A correção fecha um pipe de entrada no orquestrador e utiliza `subprocess.run`
com `stdin=PIPE` no executor (a comunicação fecha o pipe sem conteúdo). A regressão
exercita o leitor instalado sem terminal, sem criar usuários HTTP. `DEVNULL` não
é suficiente neste Windows: o dispositivo NUL pode retornar `isatty() == True`.

Há também uma falha comprovada na aceitação de fases: o executor anterior marcava
`concluido` mesmo com zero requisições ou erros tardios no console e saída zero.
Agora verifica artefatos, quantidade de usuários e erros; retorna 2 para falha de
validação, preservando `codigo_saida` real e `erros_validacao` nos novos metadados.
Registra todos os eventos de usuários e não sobrescreve o primeiro marco válido
quando ocorre uma nova redução/spawn.

O erro de CSV fechado ocorre no encerramento da medição, depois de transcorrida
a janela sem requisições. Não há evidência de que ele tenha causado os zero usuários.
Na biblioteca instalada, o código de saída é determinado antes de fechar arquivos
do writer; uma exceção tardia pode coexistir com saída zero. Não foi alterada a
biblioteca: esses erros invalidam a fase, inclusive o erro de usuário já em `stopping`.

## Amostras Linux e relógios

Os metadados associam corretamente aplicação I/O, C4, dois usuários e repetição 2002.
O intervalo nominal direto é de `2026-10-08T23:05:16.292398+00:00` a
`2026-10-08T23:06:15.512252+00:00`. O offset incorporado é
Linux menos Windows = `+0.088748 s`; portanto soma-se `-0.088748 s` ao UTC Linux.

Foram lidas 199 amostras de sistema, de `23:04:43.150482+00:00` a
`23:08:01.210044+00:00`. Após correção, 58 intervalos de CPU ficam inteiramente
dentro dos marcos nominais. Não houve erro de parsing ou insuficiência de cobertura.
O histórico não contém dois snapshots com os dois usuários planejados; a janela
válida é ausente. Por isso as médias Linux não foram calculadas e
`amostras_sistema` foi zero. O consolidado agora explicita a disponibilidade e a
contagem nominal separadamente, sem transformar ausência de carga em medição válida.

## Recuperação futura, somente das duas tarefas

Antes de executar, confirme C4 e a configuração I/O exigida pelo orquestrador
(dois workers, diagnóstico habilitado, `IO_FSYNC=1`), espaço livre, SSH e ausência
de outra execução. Use as mesmas opções SSH/raiz VM da campanha original se forem
diferentes dos padrões. Nenhum comando abaixo foi executado nesta correção.

`--retomar` pula tarefas concluídas após conferir seus hashes, executa tarefas
planejadas e recusa uma tentativa com estado falha/interrompido/em execução.
A numeração é `base + 10 * (tentativa - 1) + repeticao_logica`.
R2002 não pode ser reusada: a segunda tentativa da repetição lógica 2 será R2012.
Não edite índices ou manifestos. O próprio orquestrador registra a nova tentativa
e atualiza seus índices, mantendo a falha histórica.

```powershell
cd D:\atividade-2-poi
$env:TEMP = 'D:\atividade-2-poi\.temp'
$env:TMP = $env:TEMP

# Nova tentativa física R2012; somente I/O, dois usuários, repetição lógica 2.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C4_01 --cenario C4 --confirmar-provisionamento C4 --aplicacao io --usuarios 2 --repeticao 2 --base-repeticao 2000 --tentativa 2

# Após conferir o resultado anterior: R2003 já planejada, tentativa original 1.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C4_01 --cenario C4 --confirmar-provisionamento C4 --aplicacao io --usuarios 2 --repeticao 3 --base-repeticao 2000 --tentativa 1
```

Confira os novos metadados, erros de validação, histórico, latências, cobertura
Linux e análise antes de considerar as duas tarefas válidas. R2012 substitui
logicamente a repetição 2 na análise final; não a inclua junto com R2002 como se
fossem repetições independentes. Uma nova falha requer outra tentativa física,
jamais remoção ou sobrescrita dos diretórios anteriores.
