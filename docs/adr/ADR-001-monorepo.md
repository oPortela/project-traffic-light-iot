# ADR-001 — Monorepo

Status: adotado; revisão da equipe pendente.

## Contexto
O semáforo é o primeiro projeto integrado da plataforma proposta no roadmap.

## Alternativas consideradas
Repositório separado ou monorepo com contratos compartilhados.

## Decisão
Mover aplicação, assets e testes para `projects/traffic-light`.
Manter dependências na raiz e contratos em `contracts`. O pacote compartilhado se chama
`iot_shared`: não criar pacote Python chamado `platform`, pois sombrearia a biblioteca padrão.
O futuro diretório `platform/` poderá organizar serviços com pacotes próprios.

## Consequências
Uvicorn recebe `--app-dir projects/traffic-light`; pytest configura caminhos no
`pyproject.toml`. Imports `app.controller` e lógica de domínio permanecem iguais.
