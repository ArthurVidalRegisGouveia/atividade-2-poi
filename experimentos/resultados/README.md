# Resultados experimentais

`publicados/` contém as cópias revisadas para versionamento dos experimentos
locais de memória e I/O e das respectivas saídas do pytest.

Os arquivos originais JSON/TXT permanecem nesta pasta, preservados localmente
e ignorados pelo Git. Os scripts de monitoramento continuam produzindo novos
originais aqui; revise novas execuções antes de acrescentá-las a `publicados/`.

Nas cópias públicas, caminhos absolutos do projeto foram substituídos por caminhos
relativos com `/`. As saídas do pytest foram convertidas de UTF-16 para UTF-8.
Tempos, contadores, respostas HTTP, metadados técnicos e hashes das aplicações
foram preservados. Não foram encontrados nomes de usuário, e-mails, credenciais
ou tokens nos quatro arquivos revisados; isso não substitui a revisão de novas
coletas, especialmente de mensagens de erro.

Não use os dados locais como resultados da VM Ubuntu: as condições, ferramentas
de medição e limitações estão descritas nos relatórios em `docs/`.
