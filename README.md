# Mimic

> Entenda o alvo. Gere a wordlist que ele realmente usaria.

```
    __  ___________  _______________
   /  |/  /  _/  |/  /  _/ ____/
  / /|_/ // // /|_/ // // /
 / /  / // // /  / // // /___
/_/  /_/___/_/  /_/___/\____/
```

![CI](https://github.com/sanmirgabriel/mimic/actions/workflows/ci.yml/badge.svg)

## O problema que o Mimic resolve

Wordlists famosas (`rockyou.txt` e afins) são vazamentos majoritariamente
americanos/globais. Elas são ótimas pra achar `password123` ou gíria de cultura
pop americana — e praticamente inúteis pra achar o padrão de senha que aparece
de verdade em ambiente corporativo brasileiro.

Em pentest real no Brasil, o padrão dominante não é palavra de dicionário solta.
É **estrutura + contexto pessoal do alvo**:

```
Mudar@123
Flamengo@0405
```

Nome do time + data de aniversário + caractere especial é uma senha mais
provável, em produção, do que qualquer entrada aleatória de wordlist
americana. O Mimic existe pra gerar esse tipo de candidato — não por acaso,
mas de forma estruturada, a partir de um perfil do alvo.

## Como funciona

O motor é um pipeline de **mutators** (transformações) que rodam em
**estágios compostos**: a saída de um estágio vira a entrada do próximo. Isso
é o que permite combinações reais como caixa + leet-speak + sufixo numérico
saindo do mesmo candidato — não ramos isolados que nunca se cruzam.

```
perfil do alvo ──▶ palavras-base ──▶ [Case] ──▶ [Leet] ──▶ [Affix] ──▶ policy ──▶ saída
                                        │
                                  (Combine e Reverse entram
                                   como estágios à parte)
```

Exemplo: a partir de `time_futebol=Flamengo` + `data_nascimento=05/09/2000`,
o pipeline gera candidatos como `Flamengo@0905`, `Fl@mengo0905`, entre outros —
compondo transformação de caixa, leet parcial e sufixo de data no mesmo
candidato.

## Instalação

```bash
# Núcleo (sem banner)
pip install -e .

# Com banner interativo (pyfiglet + rich)
pip install -e ".[ui]"
```

## Uso

### A partir de uma lista simples de nomes

```bash
echo -e "joao\nsilva" | mimic --leet partial --year-range 2020:2026 | hashcat -m 0 hashes.txt
```

### A partir de um perfil estruturado do alvo

Em vez de uma lista solta de nomes, você descreve o alvo e o Mimic decide
sozinho qual campo alimenta qual transformação (data vira variações de data,
não texto genérico):

```json
{
  "time_futebol": "Flamengo",
  "data_nascimento": "05/09/2000"
}
```

```bash
mimic --profile perfil.json --separators "@" --debug
```

Saída (wordlist, em stdout):
```
Flamengo0905
Flamengo@0905
Flamengo0905@
...
```

Com `--debug`, o stderr mostra a origem de cada candidato:
```
[mimic] Flamengo@0905 <- time_futebol=Flamengo + data_nascimento=05/09/2000
```

> O rastreamento de origem por candidato ainda está em consolidação para
> casos com leet-speak ativo (o padrão da ferramenta) — hoje funciona de
> forma confiável com `--leet none`; a cobertura para `--leet partial`/`full`
> está sendo fechada antes do próximo release.

### Direto pro Hydra (ataque online)

```bash
mimic --names targets.txt --numbers dates.txt --combine \
  | hydra -L users.txt -P /dev/stdin ssh://192.168.1.100
```

### Com política de senha (filtra o que não passaria numa validação real)

```bash
mimic --names names.txt \
  --min-len 8 --max-len 16 \
  --require-upper --require-digit --require-special \
  --year-range 2020:2026 \
  --output wordlist.txt
```

### Exportando regras hashcat

Em vez de expandir a wordlist inteira localmente, exporta a lógica de
transformação como arquivo `.rule`, pra crackear com aceleração de GPU:

```bash
mimic --names names.txt --year-range 2020:2026 --export-rules mutations.rule
hashcat -m 0 -r mutations.rule hashes.txt base_words.txt
```

## Referência da CLI

```
mimic [OPÇÕES]

--names ARQUIVO        Arquivo de nomes/palavras-base (lê stdin se omitido)
--profile ARQUIVO      Perfil estruturado do alvo (JSON/YAML)
--numbers ARQUIVO      Números/anos extras
--output ARQUIVO       Arquivo de saída (padrão: stdout)
--leet {none,partial,full}   Modo leet-speak (padrão: partial)
--combine               Cruza nomes entre si (joao+silva -> joaosilva, jsilva, ...)
--min-len N              Tamanho mínimo
--max-len N              Tamanho máximo
--require-upper          Exige letra maiúscula
--require-lower          Exige letra minúscula
--require-digit          Exige dígito
--require-special        Exige caractere especial
--separators CARACTERES  Separadores usados nos afixos (padrão: @!#_.)
--export-rules ARQUIVO   Exporta regra .rule do hashcat em vez de wordlist
--year-range INI:FIM     Gera anos automaticamente (ex: 2018:2026)
--max-per-word N         Teto de candidatos gerados por palavra-base
--debug                  Mostra em stderr a origem de cada candidato (com --profile)
--quiet                  Suprime progresso e banner em stderr
--no-banner              Suprime só o banner ASCII
--version                Mostra a versão e sai
```

## Por que não só usar CUPP/Crunch/Mentalist + rockyou?

- **CUPP** gera lista plana a partir de um perfil — sem combinatória entre
  transformações, sem filtro de política, sem exportação de regra.
- **Crunch** é força bruta por permutação — poderoso, mas cego ao contexto
  do alvo.
- **Mentalist** tem fluxo de GUI, sem integração de pipeline via CLI.
- **rockyou** e wordlists de vazamento famosas carregam viés de vocabulário
  americano/global, fraco pra capturar padrão comportamental brasileiro.

O Mimic tenta ocupar o espaço entre essas ferramentas: consciente do alvo
como o CUPP, com profundidade combinatória real entre transformações,
filtro de política de senha, exportação nativa de regra hashcat, e (em
construção) contexto nativo de padrão brasileiro.

## Arquitetura

```
mimic/
├── cli.py                  # ponto de entrada, parsing de argumentos
├── core/
│   ├── generator.py        # motor: compõe estágios, dedup, filtra por policy
│   ├── policy.py            # regras de aceitação de senha
│   └── sink.py               # escreve a saída (stdout ou arquivo), streaming
├── mutators/
│   ├── base.py                # contrato Mutator
│   ├── case.py                  # variações de caixa
│   ├── leet.py                    # leet-speak parcial/total
│   ├── affix.py                     # prefixo/sufixo numérico com separador
│   ├── combine.py                     # combinação entre nomes
│   ├── reverse.py                       # inversão de palavra
│   └── date.py                            # variações de data de nascimento
├── profile/
│   ├── schema.py             # estrutura do perfil do alvo
│   └── loader.py               # carrega perfil, monta plano de geração, explica origem
├── rules/
│   └── hashcat.py            # exportador de regra .rule
└── ui/
    └── banner.py              # banner ASCII (opcional, só stderr, só se TTY)
```

## Estado atual do projeto

O desenvolvimento segue em fases, cada uma fechada com teste antes de
avançar pra próxima.

- **Fase 0 — Motor de composição** — concluída. Os mutators agora rodam em
  estágios sequenciais compostos (Case → Leet → Affix), não mais em ramos
  paralelos isolados. Inclui teto configurável de candidatos por
  palavra-base e log de truncamento quando o teto corta uma fronteira
  intermediária.
- **Fase 1 — Perfil estruturado do alvo** —concluída. `DateMutator` e
  schema de perfil implementados; rastreamento de origem por candidato
  (`--debug`) funcional para `--leet none`, cobertura para leet ativo sendo
  fechada.
q  Seed de padrões brasileiros (times, palavras de reset corporativo) e
  merge com wordlists de vazamento real.
- **Fase 3 — Ranqueamento de candidatos** — planejada. Score de
  plausibilidade pra viabilizar ataque online com lockout, não só crack
  offline exaustivo.
- **Fase 4 — API/interface web** — planejada.

## Uso ético

Ferramenta feita para uso em engajamentos de pentest e red team
**autorizados**. Gerar ou testar credenciais contra sistema sem autorização
explícita do proprietário é crime na maioria das jurisdições, incluindo o
Brasil (Lei 12.737/2012 e correlatas). Uso é de responsabilidade de quem
executa.

## Desenvolvimento

```bash
pip install -e ".[dev,ui]"
pytest -v
```

## Licença

MIT