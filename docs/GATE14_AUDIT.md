# MIMIC — Gate 14: Service Catalog Expansion Audit

Auditoria independente realizada em 2026-10-16. As conclusões abaixo vêm de
nova extração da base, novas execuções e consulta documental durante este Gate;
os resultados do relatório de implementação não foram usados como aprovação.
Evidências locais desta execução: `/tmp/mimic14gate`.

## 1. Baseline e working tree

Branch confirmada: `feat/service-catalog-expansion`. HEAD/base:
`93bd6807b71fd8859a2e202dd02b6ac75020f1b4`, merge do PR #18; ancestralidade
confirmada com `git merge-base --is-ancestor`. A aprovação anterior da main em
Python 3.10/3.11/3.12 foi informação fornecida pelo operador, não CI deste diff.

Antes de editar: status completo, diff contra HEAD, staging vazio e SHA-256 dos
199 arquivos tracked/untracked registrados em `initial-files.json`, com cópias
em `initial/`. Havia 15 arquivos tracked modificados, cinco untracked da
implementação e três scripts untracked do operador. A suíte inicial passou:
**2.038 passed em 431,10 s** (`initial-tests.log`). A base extraída contém os
**1.954 node IDs históricos**, todos ainda presentes no conjunto final.

Lidos o relatório integral, ADR 0014, ADR 0010, BACKLOG, Gates anteriores
relevantes e o diff real. Nenhum commit, push, merge, staging ou autenticação
externa foi realizado. Não houve trabalho no Block 15.

## 2. Inventário antes/depois

Inventário por importações independentes da base e da branch, incluindo todos
os campos serializados, perfis, operandos comuns e CSVs:

| Medida | Base | Branch |
|---|---:|---:|
| ServiceKnowledge | 7 | 13 |
| ServiceProfile | 7 | 13 |
| DefaultCredential | 2 | 4 |
| Serviços sem par documentado | 5 | 9 |
| Versões de introdução dos registros | v1 | v1 e v2 |
| URLs oficiais únicas | 9 | 20 |
| Aliases | 12 | 23 |
| Tokens de perfil | 16 | 23 |
| Roles de perfil | 13 | 19 |
| Registros históricos removidos/alterados | — | 0 |

Entregues os seis serviços propostos: Zabbix, SonarQube Server, Jenkins,
Apache Tomcat, Redis e OpenSearch. Dois novos pares; os outros quatro serviços
têm conhecimento de autenticação sem par associado. Os sete serviços, sete
perfis e dois pares antigos são prefixos integralmente idênticos aos da base.
Arquivos: `base-inventory.json` e `initial-inventory.json`. Quantidade adicional
não constitui evidência de eficácia ou de prevalência de uma senha.

## 3. Revisão de arquitetura

`catalog.py` contém tuplas locais de fatos e pares, validação, busca e CSV;
`builtins.py` contém operandos contextuais. Os modelos frozen separam fatos,
perfis, pares e vocabulário independente. CLI e Web consultam o mesmo catálogo.
Não há registro de plugins, ORM, esquema novo, scraping ou segunda engine.

`planning.py` usa somente os IDs explicitamente selecionados para obter tokens
e roles. `GenerationService` prepara os mesmos seeds/templates e passa pela
mesma engine, dedup, política e ranking. Requests/Jobs mantêm seu contrato.
Comparação byte a byte de **38 arquivos protegidos** da base, cobrindo Core,
mutators, ranking, application, Jobs, persistência, rules e planejamento:
nenhuma alteração (`invariants.json`).

Um Generated Candidate é uma hipótese com proveniência causal; não certifica
uma credencial. DefaultCredential permanece um par documental condicionado.
CommonCredentialVocabulary são listas independentes, sem produto cartesiano
implícito ou associação a uma tecnologia.

## 4. Matriz de evidências oficiais

As **11 URLs novas do catálogo foram reabertas neste Gate**. Foram também
consultadas as páginas iniciais indicadas no pedido e documentação atual para
conferir limites, sem ampliar automaticamente registros fixados em releases.
Domínios/projetos conferidos; nenhuma referência foi tratada como instrução
para executar comandos ou acessar instalações.

| Serviço | Afirmação | Fonte oficial | Escopo de versão | Condição de implantação | Evidência | Restrições | Resultado |
|---|---|---|---|---|---|---|---|
| Zabbix | Login inicial `Admin/zabbix`; recomendação de trocar a senha | [Quickstart 7.4](https://www.zabbix.com/documentation/7.4/en/manual/quickstart/login) | 7.4 | Frontend inicial descrito pelo quickstart | Seções Login e configuração do usuário; [current](https://www.zabbix.com/documentation/current/en/manual/quickstart/login) identifica 7.4 na consulta | Capitalização significativa; não comprova contas modificadas, agentes ou imagens customizadas | Confirmada com qualificação |
| SonarQube Server | Conta inicial `admin/admin`, permissão Administer System | [User management 2025.1](https://docs.sonarsource.com/sonarqube-server/2025.1/instance-administration/user-management/introduction) | 2025.1 | Conta administrativa criada automaticamente | Seção relativa à conta administrativa | Não prova validade depois da alteração da conta | Confirmada |
| SonarQube Server | Primeiro setup solicita troca; escopo Docker/ZIP Developer/Enterprise | [First setup](https://docs.sonarsource.com/sonarqube-server/2025.1/try-out-sonarqube), [Installation scope](https://docs.sonarsource.com/sonarqube-server/2025.1/setup-and-upgrade/install-the-server/introduction) | 2025.1 | Instalação de nó único nas edições indicadas | As duas instruções de setup e a introdução delimitam o cenário | Sem extrapolação para Cloud, Community Build ou outras releases | Confirmada com qualificação |
| Jenkins | Senha de desbloqueio gerada por instalação; criação do primeiro administrador | [Offline setup wizard](https://www.jenkins.io/doc/book/installing/offline/) | Handbook sem versão fixada | Novo controller usando o wizard | Unlocking Jenkins e criação do primeiro usuário | Não há senha universal nem intervalo de releases demonstrado; provisionamentos podem diferir | Confirmada com qualificação |
| Apache Tomcat | Arquivo distribuído não habilita usuários; exemplos comentados são ignorados | [tomcat-users.xml, tag 11.0.27](https://github.com/apache/tomcat/blob/11.0.27/conf/tomcat-users.xml) | 11.0.27 | Arquivo de fábrica dessa tag | XML parseado: zero elementos filhos de usuários; exemplos estão em comentários | Não descreve todos os Realms, pacotes ou containers instalados | Confirmada |
| Apache Tomcat | Manager precisa de conta com role configurada, como manager-gui | [Tomcat 11 Manager](https://tomcat.apache.org/tomcat-11.0-doc/manager-howto.html) | Linha 11, cotejada com a tag | Acesso ao aplicativo Manager | Seção de configuração de acesso; [10.1](https://tomcat.apache.org/tomcat-10.1-doc/manager-howto.html) e [main](https://github.com/apache/tomcat/blob/main/conf/tomcat-users.xml) foram conferidos como apoio | Exemplos de usuários e roles não são pares iniciais habilitados | Confirmada com qualificação |
| Redis | ACL desde 6; requirepass depende de configuração; protected mode limita o caso padrão sem senha | [Open Source security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/) | ACL Redis 6+; página latest | Redis Open Source conforme configuração descrita | Seções Authentication e Protected mode | Não equivale a senha fixa nem a acesso remoto universal | Confirmada com qualificação |
| Redis | Usuário default com nopass autentica conexões sem AUTH | [ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/) | Redis 6+ | ACL default descrita, antes de configuração específica | Explicação de default e nopass; nopass também aceita qualquer senha | Ausência de requisito de senha não é par com senha vazia | Confirmada com qualificação |
| Redis | Redis Cloud exige senha e suporta RBAC | [Cloud database security](https://redis.io/docs/latest/operate/rc/security/database-security/) | Página de Cloud consultada | Bancos Redis Cloud | Seção de proteção de acesso ao banco | Credenciais Cloud são separadas da configuração OSS | Confirmada com qualificação |
| OpenSearch | Demo installer exige senha admin personalizada desde 2.12, para novos clusters | [Demo configuration 2.12](https://docs.opensearch.org/2.12/security/configuration/demo-configuration/) | A partir de 2.12 no fluxo descrito | Docker/TAR/Windows/Helm/RPM/DEB com Security demo installer | Aviso de instalação e variável OPENSEARCH_INITIAL_ADMIN_PASSWORD | Clusters já configurados não são afetados; produção/custom/managed requerem evidência própria | Confirmada com qualificação |

A [documentação atual do OpenSearch](https://docs.opensearch.org/latest/security/configuration/demo-configuration/)
confirma a transição em 2.12; requisitos de complexidade atuais não foram
retroativamente importados como fatos da release fixada. A exclusão de um
cenário acima é limite da evidência, não afirmação de que toda implantação
excluída necessariamente se comporta de outra forma.

O navegador de pesquisa não recuperou a página GitHub da tag Tomcat pelo cache.
Nova consulta HTTP direta à **URL exata** retornou 200; o arquivo raw da mesma
tag foi baixado e parseado separadamente. Evidências `tomcat-blob.html` e
`tomcat-users-11.0.27.xml`; SHA-256 do XML:
`2622dee23b25d942b6b7ce8dc6b3568614746fc5242c6858752ee6d0d0b6491e`.
Não foi ausência de consulta externa nem reutilização do download da implementação.

Os nove URLs históricos foram preservados por comparação integral. Este Gate
não apresenta essa invariância como nova verificação documental de cada fato
dos sete serviços anteriores. Não houve afirmação nova contradita ou não
verificável entre as afirmações efetivamente entregues, dentro dos escopos acima.

## 5. Fatos confirmados e rejeitados

Confirmados os fatos com as qualificações da matriz. Rejeitadas como inferências
sem suporte: usar exemplos comentados de Tomcat como contas ativas; converter
um segredo gerado por instalação em senha universal; associar valores comuns
a qualquer serviço; converter nopass em par com senha vazia; aplicar demo
histórica a instalações modernas sem evidência de versão. Essas hipóteses não
constam dos pares da implementação e foram cobertas por testes negativos.

Nenhum registro precisou de remoção, nova fonte ou alteração de escopo neste
Gate. A consulta ocorreu em 2026-10-16; documentação mutável poderá exigir nova
curadoria em revisão futura, com preservação das versões históricas.

## 6. Credenciais documentadas e applicability

| Registro novo | Par exato | Associação auditada | Condições preservadas |
|---|---|---|---|
| zabbix-initial-admin | `Admin` / `zabbix` | Fonte 7.4 presente em references, com título idêntico | Frontend inicial; case-sensitive; troca imediata recomendada; customizações e outras releases fora do escopo |
| sonarqube-initial-admin | `admin` / `admin` | Fonte de user management 2025.1 presente em references; instalação cotejada em duas fontes adicionais | Developer/Enterprise, Docker/ZIP, primeiro setup; troca solicitada; não cobre conta alterada ou outro produto |

Ambos: `type=documented_default`, `record_version=1`, introdução em
`service-catalog-v2`, version_scope explícito e restrictions não vazias.
As fontes da seção 4 sustentam pares iniciais; não são exemplos fictícios nem
contas cujo usuário deva criar manualmente com esses valores. Não se afirma
validade numa instalação concreta e não se tentou login algum.

## 7. Serviços sem default universal

Jenkins, Tomcat, Redis e OpenSearch retornam zero pares no catálogo. Isso
expressa falta de par aplicável documentado nesta coleção, não prova ausência
de autenticação. Todos continuam listados, pesquisáveis e com notas, referências
e perfis úteis. `test_commented_accounts_and_unassociated_common_values_are_not_pairs`
e os quatro testes documentais do Block 14 fixam esses limites.

## 8. Versionamento

`service-catalog-v1` resolve exatamente a coleção antiga e seu CSV; v2 é uma
visão cumulativa, com registros antigos ainda marcados v1. Novos IDs só resolvem
em v2. IDs/versões desconhecidos falham explicitamente. Nenhum ID histórico
foi reaproveitado com novos tokens, URLs, restrictions ou conteúdo.

Os sete ServiceProfiles antigos conservam `knowledge-v1`; os seis novos têm
`knowledge-v2`. `KNOWLEDGE_VERSION=knowledge-v1` no summary/template continua
identificando o algoritmo/operandos comuns existentes, conforme ADR 0014;
não é um hash da enumeração de todos os serviços disponíveis. A revisão do
perfil é exibida separadamente na CLI/Web. `record_version=1` identifica a
revisão do registro; version_scope é texto de aplicabilidade documental.

Golden fixture conferida com extração nova da base, roundtrips JSON dos modelos
e requests, visões coexistentes e oito Jobs verdadeiramente anteriores à
expansão passaram. Não houve migração nem exigência retroativa de novos campos.

## 9. Integridade referencial

| Matriz adversarial | Resultado observado |
|---|---|
| Knowledge sem profile; profile sem knowledge | Rejeitados por igualdade de conjuntos de IDs |
| IDs de serviço/perfil duplicados | Rejeitados |
| Alias repetido por case/whitespace; alias entre serviços | Rejeitados por normalização; resolução previsível |
| Par com serviço ausente ou fonte/título fora de references | Rejeitado |
| Mesmo serviço/usuário/senha/scope com outra prosa | Rejeitado como duplicação |
| ID inválido; coleção/revisão/profile version inválidos | Rejeitados |
| HTTP, userinfo, hostname malformado, porta inválida, controles em URL | Rejeitados |
| Texto vazio, nulo, tipos incorretos, >4096 caracteres | Rejeitados nos campos aplicáveis |
| C0/C1, surrogate, newline, separadores Unicode, controles de formato | Rejeitados |
| Restrictions vazias; novo par sem scope | Rejeitados |
| Scope em prosa contradizendo a fonte | Estruturalmente aceito; exige revisão documental humana |

Última linha reproduzida substituindo apenas o scope do par Zabbix por
`SonarQube Server 2025.1`: validate_catalog aceita texto válido. O validador não
pretende interpretar prosa ou provar fatos a partir de URLs. Os registros
entregues foram conferidos manualmente; não se adicionou parser especulativo
de versões. Limitação registrada na seção 31, não ocultada como teste de rejeição.

Testes existentes de Gates 10/14 e `test_gate14_audit.py` exercitam os demais
casos. Os modelos destacam dados mutáveis recebidos em tuplas frozen.

## 10. ServiceProfile versus ServiceKnowledge

Knowledge fornece descrição, aliases, referências e notas; não alimenta
automaticamente a geração com sua prosa. Perfil fornece somente:

| ID | Tokens | Roles convencionais/contextuais |
|---|---|---|
| zabbix | zabbix | Admin |
| sonarqube | sonarqube, sonar | admin |
| jenkins | jenkins | administrator |
| tomcat | tomcat | manager-gui |
| redis | redis | default |
| opensearch | opensearch | admin |

Um nome/role não afirma conta habilitada nem sua senha. A semântica do template
e as Origins existentes foram preservadas. A coincidência entre um token de
produto e um valor documental não demonstra leitura do par pela engine;
o teste canário altera o catálogo de pares sem alterar nenhum candidato.

## 11. Common-v1 invariance

to_dict integral, ordem, usernames/passwords, descrição, ID/versão/classificação,
CSV e operandos comuns foram comparados com a base. Nenhuma diferença.
São seis usernames e seis passwords independentes, não seis pares. Opt-in de
passwords mantém ready seeds sem mutação/combinação; Corporate BR mantém seu
opt-in histórico de Common/PT-BR e não passa a selecionar serviços.

## 12. Busca e descoberta

ID, display name, aliases, tokens, descrição/categoria textual e nomes parciais
funcionam com strip/casefold e ordem da tupla. Testados novos/antigos, consulta
vazia, SQL/termos ambíguos, caixa mista, Unicode sem resultado, 10.000 caracteres
na função/CLI e payload HTML. Busca Web é limitada a 200 caracteres e rejeita
201 com 422. Sem traceback ou script executado nos casos testados.

Categorias não têm schema próprio. `CI/CD`, `DevSecOps`, `cache` e `Java`
encontram os registros pela descrição canônica. Busca não faz stemming,
tradução de consultas ou busca por nomes convencionais de contas; não se
promete que uma categoria traduzida encontre a descrição inglesa. As consultas
do harness são serializadas e comparadas nos três hash seeds.

## 13. CLI

Exercitados list/search/show dos 13 serviços, list de pares global/por serviço,
categoria common, export CSV, help e erros. Os seis novos IDs têm testes
específicos. Sem pares, a saída diz que não há default documentado nesta
coleção. Nos pares, source/applicability/restrictions acompanham os valores.

**31 operações normais de catálogo** passaram com socket resolution/conexão
e subprocess.Popen substituídos por funções que falham se chamados. A CLI
continua offline. Erros de argumentos usam argparse; ID desconhecido retorna
1 e falha de exportação retorna 2. A CLI canônica continua em inglês.

Comparação real de **12 cenários legados**: sintaxe antiga/`generate` ×
wordlist/rules × none/partial/full. stdout, stderr e arquivo de regras
coincidiram; somente o caminho do arquivo de saída nos dois processos foi
normalizado (`cli-legacy.json`). Nenhum ajuste na geração CLI foi necessário.

## 14. CSV/escaping/publicação

csv.writer mantém ordem/escaping de aspas, vírgulas, pontuação e Unicode.
Valores iniciados por `=`, `+`, `-`, `@`, inclusive após whitespace, recebem
apóstrofo na representação para planilhas. O valor canônico no modelo fica
intacto; CSV seguro não promete roundtrip literal desse prefixo. Controles e
campos excessivos são rejeitados antes da exportação. Applicability concatena
restrictions e scope, com source_url na própria linha.

Exportação usa staging no diretório de destino, flush/fsync e link atômico
que recusa destino existente, inclusive symlink. Testados arquivo existente,
symlink válido/dangling, diretório, pai ausente, escrita parcial, fsync,
publicação e dois escritores reais sincronizados em os.link. Na corrida:
um retorno 0, outro 2; somente um arquivo completo, byte-idêntico ao CSV
canônico, sem staging restante.

Defeito G14-01: falha em fdopen vazava o raw fd. Corrigido conforme seções
27–28; agora todos os cinco caminhos de abertura/escrita/fsync/publicação/
sucesso fecham o descritor. Não foi alterado o contrato de publicação.

## 15. Web PT-BR/EN

Rotas `/services`, `/services/{id}`, busca, common, empty state e navegação
contextual passaram em TestClient e Firefox. **636 chaves por locale**, sendo
106 de catálogo/navegação; igualdade de conjuntos e placeholders preservada.
Descrições, notas, restrictions, scopes e labels dos novos registros possuem
traduções, sem traduzir produtos, IDs, URLs ou os valores dos pares.

CSP existente preservada, HTML autoescaped e POST de geração sem CSRF retorna
403. Dados hostis injetados em display name, alias, username e password são
texto escapado; q hostil não executa script. Abrir catálogo/seleção não cria
Jobs. Cada link novo preseleciona somente seu próprio serviço e deixa Common
desmarcado. Não há migração, mudança de CSS nem comportamento de busca remoto.

## 16. Segurança e privacidade

Revisados query injection, XSS refletido/armazenado por fixture, URLs, controles,
tipos nulos/incorretos, CSV e entradas longas. URLs são dados HTTPS com hostname
validado; não são carregadas pelo servidor. Scripts/styles do catálogo são
locais. Não foi introduzido SSRF, leitura de catálogo como código, subprocess
de descoberta, autenticação ou teste de credenciais.

Erro local do CLI export pode incluir o caminho que o próprio operador forneceu,
como já ocorria antes; não é novo canal Web nem traceback. Logs dos cenários
de catálogo não registraram dados pessoais. Fixtures são sintéticas. Download
de documentação foi ação desta auditoria, separada do runtime do produto.

## 17. Separação catálogo/geração

Fixture de par para o novo serviço Zabbix, com username/password canários
exclusivos, foi instalada por monkeypatch. Nos seis contextos exigidos, a
geração antes/depois ficou idêntica em todos os metadados; chamar list_credentials
durante geração causaria falha imediata no teste. Nenhum canário foi emitido.

Sem serviço, nenhuma Origin `service.*`; com seleção, somente contribuições
do perfil escolhido. Corporate BR não adiciona serviço. Engine, score-v1,
diverse-v1 e candidate-family-v1 são os mesmos bytes da base. Caps, dedup e
primeira proveniência causal foram também cobertos pelas regressões históricas.
Não se inventou uma Origin de par documentado.

## 18. Comportamento de novos serviços

Harness independente `tests/gate14_evaluation.py contexts`: referência 2026,
organização Synthetic Brasil/alias SB quando aplicável, partial, separadores
`@!`, cap 30 e Quick 100; Corporate BR usa diverse-v1 do preset. Medições
observacionais, sem alegação de eficácia de ataque:

| Contexto | Avaliados | Retidos | Famílias retidas | Tempo s | Peak RSS KiB |
|---|---:|---:|---|---:|---:|
| Organização sem serviço | 992 | 100 | organization-role 100 | 0,019 | 24640 |
| Organização + WordPress | 1705 | 100 | organization-role 100 | 0,030 | 24856 |
| Organização + Zabbix | 1364 | 100 | organization-role 100 | 0,022 | 24856 |
| Somente Zabbix | 124 | 100 | service-role 60; other 40 | 0,002 | 24856 |
| Corporate BR sem serviço | 2148 | 100 | organization-role 94; organization-number, organization-other, other, ptbr-number, ptbr-other, ready: 1 cada | 0,042 | 25240 |
| Corporate BR + Zabbix explícito | 2520 | 100 | organization-role 92; as seis anteriores, organization-service e service-role: 1 cada | 0,045 | 25240 |

Origins completas em `contexts.json`. Contagens por candidato retido podem
somar mais de 100 por haver múltiplas causas. Organização sem serviço:
name/role/common_number=100 cada. Com WordPress: name=58, alias=42,
service.wordpress.role=100, common_number=100. Com Zabbix: mesmas contagens,
role de zabbix. Somente serviço: token=89, role=71, common_number=98.
Corporate sem serviço: name=96, role=95, common_number=97, common_password=1,
dataset=2. Corporate com serviço: name=61, alias=34, token=3, role=93,
common_number=97, common_password=1, dataset=2. Zero duplicatas retidas.

Todos os seis perfis novos são também exercitados individualmente em geração,
scoring, famílias, requests e API/Jobs nos testes de expansão. Não se infere
qualidade superior por terem sido avaliados mais candidatos.

## 19. Compatibilidade com serviços históricos

Nova referência executada a partir de `git archive` do SHA exigido, sem usar
o golden da implementação como autoridade. **77 cenários, zero diferenças de
contrato**: nenhum/cada um dos sete serviços × none/partial/full ×
Exhaustive/Quick/Focused; mais ACME+WordPress, target/profile/data, PT-BR/Common,
packs seed/ready e Corporate BR/diverse-v1. Cap 30 na matriz principal;
fixture histórica ACME usa sua configuração original, sem esse cap reduzido.

Comparados request JSON, summary, warnings, evaluated/retained, SHA-256 de todos
os resultados serializados (Origins, Transformations, score/components,
rank/encounter/selection), famílias e SHA-256 dos bytes da wordlist com newline
e ordem preservadas. Só tempo/RSS são excluídos da igualdade. Resultado histórico
ACME+WordPress 2026: **159.175 avaliados, 100 retidos** nas duas árvores.

Reprodução a partir do checkout, com ambiente virtual existente:

```bash
mkdir -p /tmp/mimic14gate/base
git archive 93bd6807b71fd8859a2e202dd02b6ac75020f1b4 | tar -x -C /tmp/mimic14gate/base
PYTHONPATH=/tmp/mimic14gate/base venv/bin/python -B tests/gate14_evaluation.py historical > /tmp/mimic14gate/historical-base.json
PYTHONPATH="$PWD" venv/bin/python -B tests/gate14_evaluation.py historical > /tmp/mimic14gate/historical-final.json
```

O script executado por caminho usa seu diretório tests em sys.path; PYTHONPATH
seleciona a árvore mimic importada. Comparar cada campo dos dois JSONs exceto
`seconds` e `peak_rss_kib`, que são medições. Packs usam os mesmos refs e bytes;
seus diretórios temporários não foram usados para mascarar proveniência.

## 20. Jobs/snapshots

`jobs-create` rodou importando a base e criou oito Jobs em
`/tmp/mimic14gate/historical-job-data`: os sete serviços antigos e Corporate BR
sem serviço. Após parar os workers, `jobs-reopen` rodou importando a branch
sobre a mesma persistência. Todos completed, snapshots intocados, replay
determinístico e wordlist completa igual byte a byte, incluindo newline.
Previews completos e downloads API após restart coincidiram.

`jobs-base.json` e `jobs-final.json` são integralmente iguais, inclusive os IDs
reais dos mesmos Jobs. Na verificação de hash seeds, Jobs novos têm UUIDs
diferentes: somente esses IDs são excluídos da projeção determinística; requests,
previews sem job_id, contagens e digests não são filtrados. Não há migração ou
campo novo obrigatório em snapshot antigo.

## 21. Hashcat bundle

`mimic/rules` está byte-idêntico à base. Nove configurações históricas de bundle
comparadas base/branch: três leet × score/diverse, mais partial omission,
empty partial e literal-only. Todos os arquivos e manifests têm hashes iguais
(`bundles-base.json`, `bundles-final.json`). Os mesmos nove casos foram
comparados entre os três hash seeds, sem normalizar manifest.

Wheel e sdist instalados passaram separadamente com Hashcat real **6.2.6**:
Synthetic Aa, inteligência desativada, leet none, anos 2025:2026 e
`--hashcat-verify`. Cada execução emitiu **106 valores**, zero missing/extra/
duplicates, coverage complete e equivalence exact-set. O contrato afirma
igualdade de conjunto de valores UTF-8, não preservação de ordem, rank,
score, encounter ou first cause pelo formato Hashcat. Logs:
`installed-wheel-bundle.log` e `installed-sdist-bundle.log`.
Toda a suíte de regressões Hashcat também passou na execução final completa.
Nenhuma execução de Hashcat desta auditoria usa hashes ou autenticação;
apenas geração de candidatos via --stdout.

## 22. Determinismo

PYTHONHASHSEED **1, 42 e 777**, processos independentes. Catálogo serializado,
ordem, profiles, common, buscas, CSV, seis contextos com requests/summary/
warnings/result metadata/wordlist e oito Jobs novos: mesmo JSON canônico,
SHA-256 **9f4d3377a1c53e72ecbc839452c4406e0a04b751e994de2ff9be21ab730478bd**.
Nove conjuntos de bundles/manifests:
**e5a76a8e544d8dd1baea1d935479026fae3cd758939a0dd8cde84b89d153eb20**.

`gate14_evaluation.py determinism` documenta exatamente as exclusões:
clocks/RSS medidos e UUID dos Jobs criados separadamente. Não são removidos
campos de requests, scores, Origins, snapshot ou diferenças reais. Os resultados
de Jobs são ordenados pelo digest do request para neutralizar ordem de criação.
Bundles são byte-idênticos e não necessitam exclusão de campos.

## 23. Performance

Mesmo Python, dependências e configuração; import em sete processos novos
por árvore, mediana; geração em cinco processos sequenciais por cenário.
As medições ocorreram na máquina compartilhada com a suíte, portanto são
observações locais, não benchmark com isolamento de CPU.

| Medida | Base | Branch |
|---|---:|---:|
| Import catalog, mediana | 15,00 ms | 16,70 ms |
| validate_catalog, média 100 chamadas | 0,0027 ms | 0,3070 ms |
| Busca, média 900 chamadas | 0,0026 ms | 0,0067 ms |
| Detail render, média 5 por serviço | 1,50 ms | 3,04 ms |
| Geração organização sem serviço, mediana | 50,45 ms | 38,10 ms |
| Geração organização + WordPress, mediana | 32,23 ms | 31,66 ms |
| Geração organização + Zabbix, mediana | — | 26,66 ms |
| Wheel | 199189 bytes | 205476 bytes |
| Sdist | 337152 bytes | 354853 bytes |

Validação nova é mais extensa que a antiga e ainda submilissegundo para 13
serviços. Renderização mede HTTP/TestClient/templates completos. RSS da geração
dos seis contextos: aproximadamente 24–25 MiB acumulados no processo; não é
memória incremental por registro. O harness HTTP completo carrega também módulos
da aplicação; seu RSS máximo observado foi 205768 KiB nos dois processos.
As diferenças de geração não demonstram ganho causal de performance.

Quantidade carregada: 13 fatos/perfis, quatro pares, 20 URLs e 636 traduções
por locale; sem I/O remoto ou índice/cache adicional. Nenhuma regressão relevante
de tempo/memória foi demonstrada; nenhuma otimização aplicada. Amostras em
`import-performance.json`, `generation-performance.json` e `catalog-*.json`.

## 24. Firefox

Execução nova com Firefox ESR real/headless e protocolo Marionette, sem
Playwright simulado: **132 layouts** = 11 páginas × PT-BR/EN × dark/light ×
375/768/1440 px reais de viewport. Páginas: lista, common, busca com resultado,
sem resultado, hostil e os seis detalhes.

Verificados idioma/tema, ausência de chaves de tradução cruas, zero overflow
horizontal do documento, referências visíveis/quebráveis, ausência de assets
externos, número correto de pares e fontes. Tabela de pares usa scroll local
em mobile, comportamento histórico que preserva legibilidade; não foi
confundido com overflow do documento. Pesquisa/submissão/link por teclado,
travessia Tab, seleção contextual dos seis IDs e Common desmarcado passaram.
Busca hostil não criou script nem variável de execução. Nenhum Job criado.

Reprodução: `venv/bin/python -B tests/gate14_firefox.py` com Firefox ESR instalado
e portas locais 8795/2845 livres. Evidências `browser.json`, `browser.log` e
quatro screenshots mobile. Cobertura de teclado não equivale a auditoria de
leitor de tela ou conformidade WCAG completa.

## 25. Wheel/sdist

Novos builds offline da base e branch, em cópias separadas, com
`python -B -m build --no-isolation`. Instalados em **dois ambientes físicos
novos**, `/var/tmp/mimic14gate-wheel` e `/var/tmp/mimic14gate-sdist`, fora do
checkout. Dependências existentes copiadas localmente; instalação com
`--no-index --no-deps --no-build-isolation`; ambos `pip check` sem erros.

Os **103 arquivos de runtime** coincidem integralmente entre fonte, wheel,
sdist e cada instalação. Metadata/Requires-Dist são iguais à base: nenhuma
dependência nova. README e ambos fixtures do sdist presentes; nenhum dos três
scripts do operador incluído. ADRs/relatórios pertencem ao repositório e não
são recursos de runtime empacotados, conforme o comportamento histórico.

CLI instalada: lista/show de todos os novos serviços, busca SONAR e CSV.
Web instalada PT-BR/EN: detalhes/traduções, static, preview com CSRF. Geração
Corporate BR + Zabbix/diverse, API/Jobs, snapshots, download completo e preview
após restart passaram em ambas, executadas de `/tmp` sem PYTHONPATH do checkout.
Todos os módulos mimic carregados vieram do ambiente instalado.

CSV SHA-256 em ambas:
`022ecfc8b157efd9ed3b5bf05629112e3d87039dabaef0e66620523d22091b0d`.
Wordlist do Job instalado:
`f120e6fe333bf2f721066af73c9eeb9619215126f8a32c05f4de865bde2a1415`.
Logs/scripts de build, instalação e smoke estão em `packaging/`, `packaging.py`,
`installed-smoke.py` e `installed-{wheel,sdist}.log` sob o diretório de evidências.
Hashes dos artifacts são registrados em `packaging/evidence.json`; bytes
comprimidos podem variar com timestamps de build, sem alterar recursos.

O primeiro harness exigiu ADR dentro do sdist e falhou: era uma expectativa
incorreta do auditor, pois nem o sdist base distribui docs/. Corrigido o harness
para verificar README/recursos/fixtures do contrato real, sem alterar produto
ou MANIFEST por esse motivo. Aviso setuptools sobre license-table é herdado.

## 26. Python CI readiness

Runtime local: Python **3.13.5**. Sintaxe de **132 arquivos Python de mimic/tests**
parseada com `ast.parse(feature_version=(3,10))`, sem erro. Não se declara
runtime deste diff validado em 3.10/3.11/3.12. CI anterior do PR #18 não é CI
da working tree. Wheel/sdist e pytest locais passam sob o interpretador descrito;
o pipeline deve confirmar a matriz quando o operador fizer seu commit/PR.

## 27. Defeitos demonstrados

**G14-01 — Low — raw descriptor leak em falha de fdopen do exportador CSV.**
Trecho herdado criava fd com mkstemp e confiava em fdopen/context manager
para fechá-lo. Se fdopen lançasse antes de entregar o stream, finally removia
staging mas não fechava fd. Em um processo que chama main repetidamente, falhas
repetidas poderiam esgotar descritores. Sem publicação parcial ou exposição
adicional de credenciais no cenário reproduzido.

Reprodução isolada: monkeypatch de os.fdopen lança OSError após captura do fd;
main retorna 2; os.fstat(fd) ainda funciona. Teste limpa o fd vazado ao reproduzir
para não contaminar outras verificações. **Failing-before: 1 failed, 5 passed**,
somente caminho open falha (`failing-before.log`). Severidade não depende de
hipótese de autenticação/rede. Nenhum achado Critical/High/Medium demonstrado.

## 28. Correções aplicadas

Mudança mínima em `mimic/cli.py`: fdopen usa closefd=False, mantendo propriedade
do raw fd no chamador; finally fecha os.close e remove staging em finally
interno. Evita fechar ambiguamente um descritor já possuído pelo wrapper em
falha de construção. Flush/fsync e publicação exclusiva permanecem iguais.

Passing-after: cinco fronteiras + corrida passam. Testes relacionados:
**186 passed em 8,23 s**. Matriz adversarial final: **58 passed em 0,70 s**.
Comparações históricas, CLI, CSV e instalações foram refeitas com a correção.
Nenhuma alteração de fatos do catálogo, ranking, engine ou contratos de Jobs.

## 29. Testes novos

`tests/test_gate14_audit.py`: **58 casos**. Seis de ownership/publicação,
36 de tipos/texto, oito URLs, seis contextos com par canário, um de contas
comentadas/valores sem associação e um de escaping/CSRF/limite de query.
Não se enfraqueceu teste histórico para corrigir o defeito.

`tests/gate14_evaluation.py`: harness de referência histórica (77 casos),
seis contextos medidos, catálogo/performance, criação/reabertura de Jobs reais
e determinismo; roda também contra a base. `tests/gate14_firefox.py`: integração
real de navegador. Ambos são ferramentas de evidência, sem alterar runtime.
Os **84 casos de expansão** existentes no início do Gate continuam presentes.
Todos os **1.954 node IDs da base** são subconjunto dos **2.096 finais**.

## 30. Suíte completa

Inicial: **2.038 passed em 431,10 s**. Final: **2.096 passed em 416,60 s**,
sem falhas ou skips, com o comando abaixo. Aumento de 58 testes neste Gate;
nenhum dos 1.954 históricos ou 84 de expansão foi removido.

```bash
TMPDIR="$PWD/venv/gate14-validation-tmp" PYTHONDONTWRITEBYTECODE=1 \
  venv/bin/python -B -m pytest -q -p no:cacheprovider -ra --durations=25
```

TMPDIR aponta para disco para não competir com o cache/JIT do Hashcat na RAM
de /tmp. Não muda timeout, assertions ou testes. Sem verificações Hashcat
externas concorrentes à suíte. Log integral: `final-tests.log`.

## 31. Riscos remanescentes

As fontes latest/handbook são mutáveis e não provam todos os releases;
qualificações permanecem nos registros. Escopo em prosa exige curadoria humana
e pode ser estruturalmente aceito mesmo quando contraditório. Não existe import
de catálogo externo que transforme esse texto em verdade automaticamente.

Não há medição de prevalência/eficácia; mais perfis não garantem melhor seleção.
Busca segue texto canônico e tem os limites descritos. Firefox não cobre outros
browsers/leitores de tela. Python 3.10–3.12 aguarda CI do novo diff. Nenhuma
dessas limitações foi convertida em alegação de aprovação não observada.

## 32. Diff summary

Implementação anterior ao Gate: catálogo/perfis/modelos, traduções/rotas/template,
CLI de exibição, README/BACKLOG, MANIFEST, fixture v1, ADR/relatório e ajustes
de cardinalidade em cinco arquivos de testes históricos: test_gate10_audit.py,
test_gate12_5_audit.py, test_password_intelligence.py, test_service_catalog.py
e test_web_services.py. Revisados: esses
ajustes mantêm assertions históricas e acrescentam visão v1 explícita.

Gate: correção pequena de ownership no exportador; 58 testes; dois harnesses;
este relatório e notas de acompanhamento documental. Não se alterou Core,
mutators, scoring, diversity, geração, snapshots, rules ou dependências.
Diff tracked contra a base: **15 arquivos, 272 inserções e 60 remoções**;
os untracked de entrega
são inspecionados separadamente, pois git diff --stat não os inclui. O único
arquivo de produção alterado durante o Gate foi mimic/cli.py. Os demais
arquivos de produção conservam os hashes do início da auditoria.

## 33. Working tree final

Branch e HEAD permanecem os da seção 1; staging vazio. Scripts do operador
preservados, não executados, não incluídos nos pacotes ou staging. SHA-256 inicial:

| Script | SHA-256 |
|---|---|
| mimic_lab_web.py | 8596622853bc1f32e77026c95994958e2ef8ed4df52f650e86e7472866ba7c60 |
| mimic_offline_lab.py | 3b4d171d767e597c32192005cbef1f7e22118252f96ebbd99b52a44b0386c2b9 |
| mimic_offline_lab_corrigido.py | 6afc8335e0696401069e78af0cb07c856a963af39e9014f2cb5f8d284f7f31be |

Roadmap integral de Block 15 até Block 21 comparado com a base e preservado,
incluindo os títulos de fase intermediários. Hashes dos três scripts iguais
ao início; staging vazio. git diff --check, status --short, diff --stat e
diff --name-only executados após a suíte, com resultados guardados em
`final-{status,diff-stat,diff-names}.txt`. Nenhum erro de whitespace.

Tracked modificados: MANIFEST.in, README.md, docs/BACKLOG.md, mimic/cli.py,
intelligence/{builtins,catalog,models}.py, web/{i18n,routes}.py,
web/templates/services.html e os cinco testes históricos listados na seção 32.
Untracked de entrega: docs/BLOCK14_IMPLEMENTATION_REPORT.md,
docs/GATE14_AUDIT.md, docs/adr/0014-service-catalog-expansion.md,
tests/block14_evaluation.py, tests/fixtures/service-catalog-v1.json,
tests/gate14_evaluation.py, tests/gate14_firefox.py, tests/test_gate14_audit.py,
tests/test_service_catalog_expansion.py. Os três scripts do operador permanecem
untracked e fora da entrega. Nenhum outro untracked foi encontrado.

## 34. Decisão

**READY FOR COMMIT** no escopo do Block 14. Fontes e qualificações verificadas,
versões históricas preservadas, pares passivos, segurança de interfaces e
compatibilidade confirmadas pelas evidências acima. G14-01 corrigido com
failing-before/passing-after; suíte completa, Firefox, pacotes instalados e
Hashcat real passaram. As limitações da seção 31 permanecem explícitas.
Sem commit/push/merge, sem staging e sem início do Block 15.
