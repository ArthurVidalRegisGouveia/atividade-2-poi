# Análise definitiva — C2

## Seleção e método

27 execuções concluídas; nove combinações; três repetições lógicas (1, 2, 3) por combinação. Seleção restrita ao índice da campanha; base identificada nos registros: 4000. Numeração segue base + 10 × (tentativa − 1) + repetição lógica. Estados não concluídos e registros fora da base são excluídos.

As unidades independentes são as repetições, com peso igual. Média = soma dos três valores / 3; desvio-padrão amostral usa divisor n−1. Mínimo/máximo são entre repetições, não entre requisições. O p95 agregado é a média dos p95 de cada execução, não o p95 de requisições reunidas. Falhas são contagens na janela útil; vazão = respostas concluídas / duração útil. Snapshots acumulados são preservados no CSV individual, mas não usados nessas estatísticas.

Ausentes não são imputados; cada estatística informa n válido. Campos essenciais ausentes, repetições incompletas e tentativas concluídas ambíguas impedem a análise. USS/PSS/disco ausentes são explicitados; DP com menos de duas observações permanece ausente.

## Resultados observados

| Aplicação | Usuários | Vazão média (req/s) | Latência média (ms) | Média dos p95 (ms) | CPU árvore (%) | RSS (MiB) | Falhas médias |
|---|---:|---:|---:|---:|---:|---:|---:|
| cpu | 1 | 3.835 | 259.031 | 272.068 | 98.520 | 42.852 | 0.000 |
| cpu | 2 | 3.827 | 518.636 | 553.588 | 98.750 | 43.315 | 0.000 |
| cpu | 5 | 3.550 | 1398.591 | 1711.460 | 98.589 | 43.703 | 0.000 |
| cpu | 10 | 3.484 | 2793.502 | 3465.453 | 98.597 | 44.177 | 0.000 |
| memoria | 1 | 0.963 | 1026.511 | 1029.912 | 2.486 | 92.818 | 0.000 |
| memoria | 2 | 1.925 | 1028.318 | 1037.859 | 4.791 | 140.985 | 0.000 |
| memoria | 3 | 2.887 | 1030.351 | 1056.055 | 7.444 | 191.798 | 0.000 |
| io | 1 | 5.429 | 182.940 | 256.253 | 11.885 | 43.223 | 0.000 |
| io | 2 | 5.732 | 346.923 | 438.264 | 12.839 | 43.694 | 0.000 |

Escrita no dispositivo explicitamente selecionado (não somada às partições):

| Usuários I/O | Dispositivo | Escrita média (MiB/s) | Total médio nos intervalos (MiB) |
|---:|---|---:|---:|
| 1 | sda | 54.790 | 3177.727 |
| 2 | sda | 57.748 | 3349.184 |

## Análise interpretativa

CPU: a vazão passa de 3.835 para 3.827 req/s entre um e dois usuários. Com cinco e dez, registra 3.550 e 3.484 req/s. As latências médias correspondentes são 1398.591 e 2793.502 ms. A CPU da árvore com dois usuários é 98.750% da capacidade VM. Esses valores são observados; limitação por CPU e fila são hipóteses compatíveis quando alta utilização acompanha aumento de latência. Variações de CPU/vazão também podem envolver agendamento e sobrecarga; estes dados não isolam a causa nem demonstram saturação monotônica.

Memória: RSS médio passa de 92.818 a 191.798 MiB entre um e três usuários. A vazão correspondente passa de 0.963 para 2.887 req/s; CPU da árvore de 2.486% para 7.444%. Retenção declarada nos consolidados (segundos): 1.0. Quando habilitada, participa do tempo de resposta: serve à observação das alocações e não representa custo de acesso à RAM. Não há demonstração de esgotamento de RAM ou saturação de largura de banda da memória; o nome Memory-bound identifica o perfil implementado.

I/O: a vazão passa de 5.429 para 5.732 req/s; latência média de 182.940 para 346.923 ms. CPU da árvore passa de 11.885% para 12.839%. Se o ganho de vazão for limitado com baixa CPU, espera por I/O/sincronização é uma hipótese, mas esses valores não comprovam saturação do disco físico do Windows. Cache, fsync, disco virtual e outras atividades podem influenciar. Os contadores são do dispositivo da VM inteira; escrita lógica de arquivos não equivale a escrita física no host.

## Limitações e avisos metodológicos

CPU da árvore é soma dos percentuais dos processos dividida pelas CPUs lógicas; 100% representa a capacidade total da VM; CPUs lógicas observadas/declaradas: 1. CPU global permanece separada, sem reconciliar contadores inconsistentes. Médias de recursos são as médias amostradas que o consolidado fornece na janela útil.

Soma RSS pode contar páginas compartilhadas mais de uma vez; não é memória privada. USS mede páginas privadas e PSS rateia páginas compartilhadas. RAM usada é do sistema inteiro. Picos são amostrados e podem perder eventos entre coletas. USS/PSS ausentes são explicitados por métrica e execução, não são zero.

Correção de relógios já aplicada pelo consolidador: UTC Windows = UTC Linux − offset (Linux menos Windows). Não se aplica correção novamente. Sondagens não comprovam sincronização perfeita nem eliminam deriva. Avisos originais são preservados por execução em avisos.csv e nos dados individuais.

Disco: um único dispositivo explicitamente selecionado, sem somar sda e sda5. A média de escrita é a média das taxas das amostras já consolidadas; total de bytes e operações cobre os intervalos selecionados, não necessariamente todos os limites UTC da carga. Não se atribui toda atividade à API.

Três repetições permitem descrição da variabilidade, não conclusões causais ou testes de significância. C2 sozinho não demonstra efeito do provisionamento comparado a outros cenários. Tentativas de recuperação podem envolver instrumentação revisada; confira os metadados antes de comparar execuções.

## Auditoria de seleção

- cpu/1: lógica 1, física R4001, tentativa 1.
- cpu/1: lógica 2, física R4002, tentativa 1.
- cpu/1: lógica 3, física R4003, tentativa 1.
- cpu/2: lógica 1, física R4001, tentativa 1.
- cpu/2: lógica 2, física R4002, tentativa 1.
- cpu/2: lógica 3, física R4003, tentativa 1.
- cpu/5: lógica 1, física R4001, tentativa 1.
- cpu/5: lógica 2, física R4002, tentativa 1.
- cpu/5: lógica 3, física R4003, tentativa 1.
- cpu/10: lógica 1, física R4001, tentativa 1.
- cpu/10: lógica 2, física R4002, tentativa 1.
- cpu/10: lógica 3, física R4003, tentativa 1.
- io/1: lógica 1, física R4001, tentativa 1.
- io/1: lógica 2, física R4002, tentativa 1.
- io/1: lógica 3, física R4003, tentativa 1.
- io/2: lógica 1, física R4001, tentativa 1.
- io/2: lógica 2, física R4002, tentativa 1.
- io/2: lógica 3, física R4003, tentativa 1.
- memoria/1: lógica 1, física R4001, tentativa 1.
- memoria/1: lógica 2, física R4002, tentativa 1.
- memoria/1: lógica 3, física R4003, tentativa 1.
- memoria/2: lógica 1, física R4001, tentativa 1.
- memoria/2: lógica 2, física R4002, tentativa 1.
- memoria/2: lógica 3, física R4003, tentativa 1.
- memoria/3: lógica 1, física R4001, tentativa 1.
- memoria/3: lógica 2, física R4002, tentativa 1.
- memoria/3: lógica 3, física R4003, tentativa 1.

## Gráficos

![vazao](vazao.png)
![latencia](latencia.png)
![cpu](cpu.png)
![memoria](memoria.png)
![escrita_disco](escrita_disco.png)
