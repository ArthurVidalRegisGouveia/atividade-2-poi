# Preparação do repositório da disciplina

O Git foi inicializado localmente com branch `main`. Ainda não há commits,
arquivos adicionados ao índice ou remoto configurado. Não foi feita publicação.

## Conteúdo destinado ao Git

- `.gitignore`, `.gitattributes`, `requirements.txt` e `README.md`.
- As três aplicações em `apps/`, os três arquivos de testes em `tests/` e os
  scripts de monitoramento em `scripts/`.
- Relatórios de memória e I/O, este guia e os arquivos `.gitkeep` existentes.
- `experimentos/resultados/README.md` e os quatro JSON/TXT revisados em
  `experimentos/resultados/publicados/`.

São ignorados ambientes virtuais, `.temp`, caches Python/pytest/ferramentas,
logs, temporários, arquivos locais de editor/sistema, `.env` e variantes
(exceto um eventual `.env.example`), `.aws` e `.codex`.
Os JSON/TXT originais diretamente em `experimentos/resultados/` permanecem
locais. Não use `git add -f` para incluir esses arquivos sem nova revisão.

Os resultados revisados preservam medidas numéricas, respostas, versões,
timestamps e PIDs necessários à interpretação. Foram normalizados caminhos
absolutos do projeto e convertidos os TXT para UTF-8. A revisão não encontrou
credenciais ou identificação pessoal nesses quatro arquivos. Mensagens de erro
e caminhos de novas execuções precisam ser revisados antes de publicar.

## Particularidade do Git neste ambiente Windows

A pasta `.git` foi criada pelo usuário do ambiente isolado
`CodexSandboxOffline`. Ao executar Git como usuário do Windows, a diferença
de proprietário provoca a proteção `dubious ownership`. A tentativa de
ajustar somente o proprietário dessa pasta foi negada pelo Windows.
Nenhuma configuração global de confiança foi alterada.

Para executar os comandos abaixo, abra uma sessão PowerShell dedicada e
configure confiança somente neste projeto e somente nessa sessão:

```powershell
Set-Location D:\atividade-2-poi
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'D:/atividade-2-poi'
```

Use uma sessão sem outras variáveis `GIT_CONFIG_*` previamente configuradas.
Feche-a ao terminar; essas variáveis não modificam arquivos de configuração
do Git nem configurações permanentes do Windows. A conferência e a simulação
de `git add` desta preparação usaram essa exceção temporária.

## Organização sugerida dos commits

Três commits iniciais facilitam a revisão por assunto:

```powershell
git add .gitignore .gitattributes requirements.txt
git commit -m "chore: prepara dependencias e regras de versionamento"

git add apps tests
git commit -m "feat: adiciona APIs CPU, memoria e IO com testes"

git add README.md docs scripts experimentos
git commit -m "docs: adiciona instrucoes e validacoes experimentais locais"
```

Esses comandos são uma proposta; não foram executados nesta preparação.
Antes de cada commit, confira o índice:

```powershell
git diff --cached --stat
git diff --cached --check
git status --short
```

Se não houver identidade Git configurada, defina apenas neste repositório:

```powershell
git config --local user.name "SEU_NOME"
git config --local user.email "SEU_EMAIL_ACADEMICO"
```

Não use credenciais ou tokens na URL do remoto. Use o mecanismo de autenticação
da plataforma da organização.

## Próxima etapa: remoto da organização

Após autorização, crie um repositório vazio na organização da disciplina, sem
README, licença ou `.gitignore` inicial, pois esses arquivos virão do projeto.
A plataforma, organização, nome, visibilidade e URL devem ser definidos pelo
responsável da disciplina; não há um destino remoto conhecido nesta etapa.

Depois dos commits locais e da confirmação da URL:

```powershell
git remote add origin "URL_DO_REPOSITORIO_DA_ORGANIZACAO"
git remote -v
git push -u origin main
```

Execute o `push` somente com autorização para publicar. Não há necessidade de
`--force`. Se o remoto já tiver conteúdo, consulte seu histórico antes de tentar
integrá-lo; os comandos acima pressupõem um remoto vazio.

## Conferência local

```powershell
git status --short --branch --untracked-files=all
git ls-files --others --exclude-standard
git check-ignore -v .venv/ .temp/ .pytest_cache/
```

A implementação das aplicações foi preservada. Esta preparação altera somente
regras de versionamento, documentação e cria cópias revisadas dos resultados;
a validação funcional mais recente permanece a suíte com 101 testes aprovados.
