# Timestamp repetido no histórico Locust — C1 / CPU / R5001

Investigação sem novas cargas, escrita de resultados ou mudança de estado histórico.

## Evidências e causa

O validador anterior reproduziu, lendo os artefatos da medição, o erro
`Histórico Aggregated duplicado ou fora de ordem`. O arquivo contém 59 snapshots
Aggregated em 58 timestamps distintos. O único par com timestamp repetido é:

| Timestamp | Usuários | Requisições acumuladas | Falhas acumuladas |
|---:|---:|---:|---:|
| 1791553806 | 1 | 3 | 0 |
| 1791553806 | 1 | 6 | 0 |

O Locust escreve `int(now)` no CSV: a fração de segundo não é preservada.
Snapshots distintos podem compartilhar o rótulo inteiro. O par acima é compatível
com essa resolução temporal; não demonstra que a mesma coleta foi duplicada.
O horário preciso das leituras não está disponível. A condição `stamp <= previous`
rejeitava igualdade, confundindo-a com retrocesso temporal.

## Correção e qualidade

O histórico permanece na ordem original, sem ordenar, eliminar linhas ou agregar
snapshots com rótulos iguais. São rejeitados timestamps menores que o anterior,
valores não finitos e contagens de usuários negativas ou fracionárias.

Quando os contadores existem, cada registro deve possuir ambos os campos
`Total Request Count` e `Total Failure Count`, com valores finitos, inteiros e
não negativos. Falhas não podem exceder requisições. Dentro da janela estável,
nenhum contador pode diminuir e o avanço das falhas não pode exceder o avanço
das requisições. Esses critérios valem tanto para timestamps iguais quanto distintos.
Snapshots sem novas requisições, com contadores iguais, também são compatíveis;
isso não autoriza interpretar timestamps iguais como duração positiva.

A comparação de progressão ocorre nos snapshots selecionados para a janela:
o reset de estatísticas na rampa, antes da janela útil, não é confundido com
regressão durante a carga. Valores numéricos inválidos são rejeitados mesmo fora
da janela. Schemas mínimos antigos sem contadores mantêm compatibilidade para
timestamps distintos; timestamps iguais sem contadores são rejeitados por falta
de informação para verificar consistência.

Timestamp inteiro continua representando `[t,t+1)`, exigindo o bucket inteiro
dentro da janela. Cada snapshot de fronteira é preservado na auditoria, mesmo
com rótulos repetidos. Todos os snapshots interiores participam da verificação
de usuários: não se omite uma queda só porque compartilha o segundo com outra linha.
São exigidos pelo menos dois timestamps numericamente distintos com os usuários
planejados, evitando contar `123` e `123.0` como horários diferentes.

Não foi necessário alterar o cálculo de duração do consolidador: ele exige
fronteiras temporais distintas e utiliza diferenças de contadores, não a soma
dos valores acumulados. As latências individuais mantêm seus próprios timestamps.
Não foram criados timestamps artificiais para distinguir as duas linhas.

Nos novos metadados, `validacao_historico` também registra
`snapshots_timestamp_repetido` e `contadores_acumulados_presentes`.

## Recuperação R5011

Uma chamada somente de leitura a `validar_fase` pode confirmar a validade dos
artefatos sob a regra corrigida, mas não promove a R5001 a concluída. Seu estado
de falha e todos os arquivos originais permanecem intactos.

Pela fórmula documentada `base + 10*(tentativa−1) + repeticao_logica`, com base
5000, tentativa 2 e lógica 1, o destino é R5011. Após confirmar C1 e as condições
exigidas pelo orquestrador, o comando para recuperar somente essa tarefa é:

```powershell
.\.venv\Scripts\python.exe scripts/experimentacao/orquestrar.py --executar --retomar --id-execucao definitivos_C1_01 --cenario C1 --confirmar-provisionamento C1 --base-repeticao 5000 --aplicacao cpu --usuarios 1 --repeticao 1 --tentativa 2
```

Esse comando não foi executado durante a correção. Use as mesmas opções SSH e
raiz VM da campanha original, se diferentes dos padrões. A R5001 não é sobrescrita.
Uma retomada ampla na tentativa original ainda encontra a falha histórica;
continuar as outras tarefas requer filtros que não selecionem R5001.
