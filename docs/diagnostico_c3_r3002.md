# Validação de aquecimento C3 / CPU / dez usuários / R3002

Investigação e reprodução local, sem novas cargas e sem regravar dados históricos.

## Evidências

O validador anterior, chamado somente para leitura sobre os arquivos reais,
retornou `Quantidade de usuários divergiu do plano durante a janela.`
O comando solicita dez usuários à taxa dez. A instrumentação registra somente
um evento de criação, com dez usuários às `00:26:03.825397+00:00`.

| Registro | UTC em 2026-10-09 | Quantidade |
|---|---|---:|
| Usuários prontos | 00:26:03.825410 | 10 |
| Histórico Aggregated | 00:26:04 até 00:26:32 | 10 em 29 snapshots |
| Último histórico Aggregated | 00:26:33 (segundo truncado) | 7 |
| Início do encerramento (evento) | 00:26:33.115135 | — |
| Fim da fase | 00:26:34.023966 | — |

O primeiro snapshot, rotulado `00:26:03`, registra zero usuários durante a
rampa; fica fora da janela estável. Não há erro HTTP ou exceção no console;
Locust termina com código zero. O console anuncia o limite de duração às
`2026-10-08 21:26:32,903` (UTC−3), antes do evento de início do encerramento.
Esse anúncio e o evento são marcos distintos, não devem ser confundidos.

`pids_janela` registra 100 respostas do worker 1208 e 93 do 1209 (193 antes
do marco de parada). `pids_apos_encerramento` registra 102 e 101 (203 após
a drenagem). O total final de 203 inclui respostas concluídas no encerramento;
não é a contagem exclusiva da janela estável. Nenhuma medição foi executada.

## Causa e reprodução

A versão instalada do Locust (2.46.7), em `locust/stats.py`, escreve
`timestamp = int(now)` em `_stats_history_data_rows`. O histórico perde a fração
de segundo. O validador comparava esse inteiro como um instante preciso:
`inicio < timestamp < fim`. Assim, incluiu o snapshot `00:26:33` com sete
usuários por compará-lo com `00:26:33.115135`.

O rótulo inteiro representa resolução de um segundo, isto é, `[33,34)`;
esse bucket cruza o início da parada. Uma coleta posterior à parada, por exemplo
às `33.515135`, produz exatamente o mesmo rótulo `33`, erroneamente classificado
como interior pelo código anterior. O teste reproduz essa condição sem HTTP.

Não há redução registrada nos 29 snapshots interiores nem nos eventos reais
de criação. O último snapshot é temporalmente ambíguo: seu horário real de
leitura não foi preservado. Portanto ele não comprova divergência na janela
estável. O falso positivo demonstrado é a classificação desse bucket de
fronteira como observação interior precisa, não uma prova do milissegundo
em que cada usuário parou.

## Correção restrita à validação

Para timestamps inteiros, somente buckets `[t,t+1)` inteiramente contidos
nos marcos da janela participam da comparação da quantidade de usuários.
Snapshots fracionários preservam sua precisão. São exigidos pelo menos dois
snapshots interiores com a quantidade solicitada; divergências interiores,
zero usuários e eventos inesperados de instrumentação continuam invalidando
a fase. Arquivos ausentes/incompletos, contagens inválidas e timestamps
duplicados ou fora de ordem são rejeitados.

Nos novos metadados, `validacao_historico` registra a política, quantidade de
snapshots disponíveis e selecionados e os snapshots ambíguos de fronteira.
Não são apagados nem substituídos dados do histórico. Não foi necessário alterar
`locustfile.py`, o orquestrador ou as APIs.

Sob a política corrigida, o aquecimento histórico passa na validação de leitura,
com 29 snapshots interiores. Isso não converte a R3002 em experimento completo:
a medição não existe e seu manifesto de falha permanece intacto. Uma alteração
real observada somente no bucket de fronteira não pode ser localizada com precisão
por esse CSV; eventos instrumentados mantêm sua verificação independente.

## Recuperação futura

Confirme C3 (duas vCPUs, 1 GiB e dois workers), diagnóstico das APIs e demais
configurações exigidas pelo orquestrador. Preserve as opções SSH/raiz VM originais
se diferentes dos padrões. Nenhum dos comandos abaixo foi executado nesta correção.

`--retomar` pula concluídas após verificar hashes e executa planejadas, mas recusa
tentativas com falha. A fórmula é `base + 10*(tentativa−1) + repeticao_logica`.
Logo, a repetição lógica 2, tentativa 2, base 3000 usa R3012. A R3002 não será
sobrescrita nem marcada manualmente como concluída.

```powershell
cd D:\atividade-2-poi
$env:TEMP = 'D:\atividade-2-poi\.temp'
$env:TMP = $env:TEMP

# Recupera somente CPU, dez usuários, repetição lógica 2, em R3012.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C3_01 --cenario C3 --confirmar-provisionamento C3 --base-repeticao 3000 --aplicacao cpu --usuarios 10 --repeticao 2 --tentativa 2

# Após conferir R3012: uma tarefa CPU planejada, R3003.
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C3_01 --cenario C3 --confirmar-provisionamento C3 --base-repeticao 3000 --aplicacao cpu --usuarios 10 --repeticao 3 --tentativa 1

# Seis tarefas I/O planejadas (1 e 2 usuários; lógicas 1, 2, 3).
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C3_01 --cenario C3 --confirmar-provisionamento C3 --base-repeticao 3000 --aplicacao io --tentativa 1

# Nove tarefas memória planejadas (1, 2 e 3 usuários; lógicas 1, 2, 3).
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C3_01 --cenario C3 --confirmar-provisionamento C3 --base-repeticao 3000 --aplicacao memoria --tentativa 1
```

Os três últimos comandos selecionam exatamente as 16 tarefas ainda planejadas.
Não use retomada ampla sem filtros: ela encontrará a R3002 histórica com falha
e será interrompida, mesmo se R3012 já estiver concluída. Tampouco use tentativa 2
para a matriz inteira: isso criaria novas tentativas de combinações já válidas.
Os índices são atualizados somente pelo orquestrador durante a execução autorizada.
