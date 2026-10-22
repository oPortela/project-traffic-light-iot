# Roteiro de Evolução — Plataforma IoT Integrada

Plano para evoluir o **Sistema Semafórico Inteligente** até a **Plataforma IoT Integrada** descrita no
*Documento de Requisitos v2.0* (UniEVANGÉLICA · Internet das Coisas), seguindo o roteiro de entrega da seção 9.2
do documento (MVP → Integração → Evolução).

> **Premissa de escopo:** este repositório passa a ser um **monorepo da plataforma**, e o semáforo atual vira o
> primeiro projeto integrado (cenário urbano, domínio `mobilidade`). Se a plataforma for construída em outro
> repositório, executar apenas a [Fase 0](#fase-0--fundação) e o item [1.4](#14-integrar-o-semáforo-como-projeto-nível-1).

---

## Sumário

1. [Diagnóstico do projeto atual](#1-diagnóstico-do-projeto-atual)
2. [Stack tecnológica (100% gratuita)](#2-stack-tecnológica-100-gratuita)
3. [Arquitetura alvo](#3-arquitetura-alvo)
4. [Estrutura do repositório](#4-estrutura-do-repositório)
5. [Roteiro de entrega](#5-roteiro-de-entrega)
6. [Critérios de aceite do MVP](#6-critérios-de-aceite-do-mvp)
7. [Rastreabilidade de requisitos](#7-rastreabilidade-de-requisitos)
8. [Riscos e mitigação](#8-riscos-e-mitigação)
9. [ADRs previstos](#9-adrs-previstos)
10. [Próximos passos](#10-próximos-passos)

---

## 1. Diagnóstico do projeto atual

O projeto é um app FastAPI único (~480 linhas): `app/controller.py` (máquina de estados), `app/main.py`
(câmera/YOLO, API, WebSocket, MJPEG), front-end estático e testes com `unittest`. É um **projeto isolado** — o
problema que a seção 2.1 do documento descreve.

| Exigência do documento | Situação atual |
|---|---|
| Mensagem canônica (JSON Schema, `id_mensagem`, `timestamp` UTC) | ❌ `snapshot()` usa formato próprio e `time.monotonic()` |
| MQTT com tópicos `{inquilino}/{site}/{dominio}/{dispositivo}/...` | ❌ Apenas HTTP e WebSocket próprios |
| Catálogo, perfis e hierarquia de locais | ❌ Inexistente |
| Persistência de séries e último estado | ❌ Tudo em memória |
| Gêmeo do dispositivo e comandos | ⚠️ `/api/control` e `/api/config` são síncronos e proprietários |
| Segurança, inquilinos e papéis | ❌ API aberta |
| Observabilidade (Prometheus, logs JSON) | ❌ Apenas `logging` padrão |
| Contratos OpenAPI / AsyncAPI | ⚠️ OpenAPI gerado pelo FastAPI, mas sem "contrato primeiro" |
| LGPD (RF-DAD-05) | ✅ Não grava imagens nem faz reconhecimento facial |
| Domínio separado do protocolo | ✅ `Controller` é puro (recebe `now` e `ids`, devolve estado) — boa base hexagonal |

**Pontos a preservar:** a máquina de estados, as regras de negócio RN01–RN05, o modo demonstração e a política
de não persistir imagens.

---

## 2. Stack tecnológica (100% gratuita)

Todos os componentes são gratuitos e de código aberto (ou de uso livre auto-hospedado). Regra registrada no
**ADR-000**: nenhuma dependência nova entra no projeto sem verificação de licença e custo.

| Camada | Componente | Licença | Observação |
|---|---|---|---|
| Serviços da plataforma | Python 3.12 + FastAPI + Uvicorn | MIT / BSD | Linguagem que a equipe já domina |
| MQTT (central e borda) | Eclipse Mosquitto | EPL / EDL | Evitar EMQX (versões recentes em licença BSL) |
| Barramento interno | NATS + JetStream | Apache 2.0 | Leve, roda em Raspberry Pi |
| Séries temporais | PostgreSQL + TimescaleDB | PostgreSQL / Apache + TSL | Gratuito auto-hospedado |
| Geometrias | PostGIS | GPL | Fase 2 (consultas espaciais) |
| Último estado | Tabela no PostgreSQL (MVP) → Valkey se necessário | BSD | Valkey é o fork aberto do Redis |
| Fila da borda | SQLite (modo WAL) | Domínio público | Cifra por registro com `cryptography` |
| Identidade e papéis | Keycloak | Apache 2.0 | OpenID Connect, 2º fator, RBAC |
| Segredos | `.env` fora do Git + Docker secrets (MVP) → OpenBao | MPL 2.0 | OpenBao no lugar do Vault (BSL) |
| API Gateway | Traefik | MIT | Roteamento, TLS e rate limit |
| Painéis | Grafana | AGPL | Gratuito auto-hospedado |
| Observabilidade | Prometheus, Loki, OpenTelemetry | Apache / AGPL | |
| NGSI-LD | Orion-LD | AGPL | Fase 2 |
| LoRaWAN | ChirpStack | MIT | Fase 2 |
| Protótipos de regras | Node-RED | Apache 2.0 | Opcional |
| Visão computacional | Ultralytics YOLOv8 + ByteTrack | AGPL-3.0 | Exige código aberto — compatível com projeto acadêmico |
| Contêineres | Docker Engine ou Podman | Apache 2.0 | Docker Desktop é gratuito para uso educacional |
| Orquestração (escala) | k3s + Helm | Apache 2.0 | Fase 3 |
| Infraestrutura como código | Docker Compose + OpenTofu | Apache / MPL | OpenTofu no lugar do Terraform (BSL) |
| CI/CD | GitHub Actions | — | Ilimitado em repositório público |
| Qualidade | pytest, pytest-cov, ruff, pip-audit | MIT / Apache | |
| Teste de carga | Locust | MIT | Em Python |
| Contratos | JSON Schema, AsyncAPI CLI, Swagger UI | Apache 2.0 | |

### Itens com possível custo e alternativas gratuitas

| Item | Alternativa gratuita | Observação |
|---|---|---|
| **SMS (RF-APP-05)** | Telegram Bot, e-mail via SMTP, **ntfy** (push auto-hospedado) | SMS real: celular Android + app open source *SMS Gateway for Android* + chip pré-pago (custo só da operadora). Registrar a substituição em ADR |
| **Hospedagem da central** | Máquina local / laboratório, ou **Oracle Cloud Always Free** (VM ARM 4 núcleos, 24 GB) | GitHub Student Pack oferece créditos extras |
| **Hardware da borda** | Segundo Docker Compose na mesma máquina ou em VM | Queda de link simulada com `docker network disconnect` |

---

## 3. Arquitetura alvo

```text
                ┌─────────────────────────── Instância central (docker-compose) ───────────────────────────┐
                │                                                                                          │
 Semáforo ──MQTT──► Mosquitto ──► ingestion ──► NATS JetStream ──┬──► storage-writer ──► Postgres/Timescale│
 (urbano)       │                  (pipeline)                    ├──► rules ──► alarmes / webhooks / tópicos│
                │   HTTP/lote ──► Traefik ──► ingestion          └──► realtime (WebSocket)                  │
                │                     │                                                                    │
                │                     ├──► registry (catálogo, perfis, locais, dispositivos, credenciais)  │
                │                     └──► api (consultas, paginação, OpenAPI)        Keycloak · Prometheus│
                └──────────────────────────────────────────────────────────────────────────────────────────┘
                                                      ▲ lotes (HTTP) quando o link volta
 Sensor de solo ──MQTT──► Nó de borda: Mosquitto local ──► fila SQLite ──► sync-worker
 (rural, simulado)                                     └──► regras locais (fase 2)
```

**Princípios** (seção 7 do documento):

- **Hexagonal em cada serviço:** domínio puro, portas (interfaces) e adaptadores (MQTT, HTTP, Postgres, SQLite).
  O mesmo domínio de ingestão roda na central e na borda com adaptadores diferentes.
- **Configuração em vez de código:** domínios, perfis e locais são dados (padrão *Type Object*). Nenhum
  `if dominio == "mobilidade"` no núcleo.
- **Contrato primeiro:** JSON Schema e AsyncAPI escritos antes do código e validados no CI.
- **Padrões EIP:** Pipes and Filters (ingestão), Dead Letter Channel (DLQ), Idempotent Receiver (deduplicação),
  Store-and-forward (borda).

---

## 4. Estrutura do repositório

```text
project-traffic-light-iot/
├── contracts/
│   ├── schemas/canonical-1.0.json     # mensagem canônica (RF-INT-01)
│   ├── asyncapi.yaml                  # tópicos MQTT
│   └── openapi.yaml                   # API REST
├── platform/
│   ├── shared/                        # validação de schema, logs JSON, métricas, modelos
│   ├── ingestion/                     # MQTT bridge + HTTP + lote → pipeline
│   ├── registry/                      # catálogo, perfis, locais, dispositivos, credenciais
│   ├── rules/                         # motor de regras + ciclo de vida de alarmes
│   └── api/                           # consultas, paginação padronizada
├── edge/                              # nó de borda: fila SQLite + sync-worker
├── projects/
│   ├── traffic-light/                 # app atual refatorado (urbano · mobilidade)
│   ├── soil-sensor-sim/               # projeto rural simulado (via borda)
│   └── examples/
│       ├── python/                    # paho-mqtt
│       ├── nodejs/                    # mqtt.js
│       └── go/                        # paho.mqtt.golang (ou C/ESP32)
├── deploy/
│   ├── docker-compose.yml             # central
│   ├── docker-compose.edge.yml        # borda
│   ├── mosquitto/                     # mosquitto.conf, ACLs geradas
│   ├── keycloak/                      # realm exportado
│   └── grafana/                       # dashboards provisionados
├── docs/
│   ├── ROADMAP.md                     # este documento
│   ├── adr/                           # registros de decisão
│   └── integrador/                    # guia do integrador (RF-INT-07)
└── .github/workflows/ci.yml
```

---

## 5. Roteiro de entrega

### Fase 0 — Fundação

**Objetivo:** reorganizar sem quebrar nada e estabelecer contratos e infraestrutura.

| # | Tarefa | Entregável | Pronto quando |
|---|---|---|---|
| 0.1 | Mover `app/`, `static/`, `tests/` para `projects/traffic-light/` | Estrutura monorepo | Testes atuais passam sem alteração de lógica |
| 0.2 | Escrever ADR-000 a ADR-004 | `docs/adr/` | ADRs revisados pela equipe |
| 0.3 | Escrever `canonical-1.0.json` (baseado na seção 4.4) | JSON Schema | Exemplo do documento valida; exemplos inválidos falham |
| 0.4 | Escrever `asyncapi.yaml` com os 4 tópicos | Contrato AsyncAPI | `asyncapi validate` passa no CI |
| 0.5 | Criar `deploy/docker-compose.yml` (Mosquitto, Postgres/Timescale, NATS) | Compose | `docker compose up` sobe tudo saudável |
| 0.6 | CI: pytest + cobertura, ruff, validação de contratos, pip-audit | `.github/workflows/ci.yml` | Pipeline verde no `main` |
| 0.7 | Migrar testes de `unittest` para `pytest` | Testes | Mesmos casos, mesma cobertura |

### Fase 1 — MVP (todos os requisitos "Essencial")

#### 1.1 Catálogo, locais e dispositivos

**Requisitos:** RF-CEN-01, RF-CEN-02, RF-CEN-03, RF-DIS-01, RF-DIS-02, RF-DIS-06, RF-SEG-04

- Serviço `registry` com o modelo `inquilino → site → area → dispositivo`, mais `dominio` e `perfil`.
- Perfil define grandezas, unidades UCUM, faixa válida e intervalo esperado de envio.
- Credencial por dispositivo (token) e revogação; arquivo de ACL do Mosquitto gerado a partir do cadastro,
  restringindo cada dispositivo aos próprios tópicos.
- Status online/offline calculado pelo intervalo esperado do perfil (sensor horário não fica offline em 5 min).
- Seed de dados com os domínios `mobilidade` e `agricultura` — **nunca** hardcoded.

**Endpoints:** `POST /api/v1/catalogo/dominios`, `POST /api/v1/perfis`, `POST /api/v1/sites`,
`POST /api/v1/sites/{id}/areas`, `POST /api/v1/dispositivos`, `DELETE /api/v1/dispositivos/{id}/credenciais`.

#### 1.2 Ingestão

**Requisitos:** RF-ING-01, RF-ING-02, RF-ING-03, RF-ING-04, RF-ING-06, RF-ING-08

Pipeline em filtros independentes e testáveis:

```text
Receber → Autenticar → Validar → Deduplicar → Ordenar → Enriquecer → Publicar (NATS)
                          └──────── rejeitadas → DLQ (com motivo) ────────┘
```

- MQTT: bridge assina `+/+/+/+/telemetria|evento|estado` no Mosquitto.
- HTTP: `POST /api/v1/ingestao` (202 / 400 com lista de erros).
- Lote: `POST /api/v1/ingestao/lote` com resultado por mensagem (5.000 com 3 inválidas → grava 4.997).
- Deduplicação por `id_mensagem` (chave única no banco + cache recente).
- Dados atrasados gravados pelo `timestamp` da medição; flag `atrasado` impede alarme "como se fosse atual".
- Medida fora da faixa do perfil marcada como `suspeita` (RF-CEN-02).

#### 1.3 Dados e regras

**Requisitos:** RF-DAD-01, RF-DAD-02, RF-DAD-05, RF-PRO-01, RF-PRO-02, RF-PRO-03, RF-PRO-05

- Hypertable `telemetria(time, dispositivo, grandeza, valor, unidade, inquilino, site, area, dominio, flags)`.
- Tabela `ultimo_estado` atualizada por upsert (sem consultar o histórico).
- Motor de regras: condições de **limite**, **ausência de dados** e **janela de tempo**.
- Ações no padrão *Strategy*: gerar alarme, chamar webhook, publicar em tópico, enviar comando.
- Alarmes com ciclo de vida `ativo → reconhecido → resolvido` e severidade; horário = horário da ocorrência.
- Anonimização: nenhuma informação pessoal identificável armazenada ou exposta.

#### 1.4 Integrar o semáforo como projeto nível 1

**Requisitos:** RF-INT-02, RF-ING-01, RF-DAD-05

Este é o item central para o projeto atual.

- Criar a porta `EventPublisher` e o adaptador `MqttPublisher` (paho-mqtt). O `Controller` permanece puro.
- Converter `monotonic` para UTC ISO 8601 **apenas na fronteira de saída**.
- Mapeamento para o contrato:

| Tópico | Conteúdo | Frequência |
|---|---|---|
| `.../semaforo-travessia-01/telemetria` | `pedestres_na_area`, `tempo_espera_s`, `ciclos` | A cada 5 s |
| `.../semaforo-travessia-01/evento` | `transicao_fase` com fase de origem e destino | A cada `transition()` |
| `.../semaforo-travessia-01/estado` | Gêmeo relatado: `wait`, `crossing`, `roi`, `modo` | Ao iniciar e ao mudar |
| `.../semaforo-travessia-01/comando` | `start`, `stop`, `reset`, `config` | Assinado pelo semáforo |

- Tópico base: `semob/centro/mobilidade/semaforo-travessia-01/`.
- **Regra LGPD:** nunca publicar frames, imagens ou bounding boxes — apenas contagens.
- O dashboard local continua funcionando (modo standalone preservado).

#### 1.5 Nó de borda

**Requisitos:** RF-EDG-01, RF-EDG-02, RF-SEG-05, RNF-04, RNF-07, RNF-10

- `deploy/docker-compose.edge.yml`: Mosquitto local + `edge` (ingestão + fila + sync).
- Fila SQLite em modo WAL com escrita transacional; ACK ao dispositivo só após commit.
- Payload cifrado por registro (chave fornecida via secret).
- `sync-worker`: envia lotes para `/api/v1/ingestao/lote` com retry e backoff exponencial; remove da fila só
  após confirmação por mensagem.
- Projeto `soil-sensor-sim` publicando `umidade_solo` e `temperatura_solo` na borda.

#### 1.6 API, segurança e observabilidade

**Requisitos:** RF-APP-01, RF-APP-07, RF-SEG-01, RF-SEG-02, RF-SEG-03, RF-INT-01, RF-INT-03, RF-OBS-01, RF-OBS-02

- Keycloak com realm da plataforma e papéis `administrador`, `gestor`, `operador`, `integrador`, `leitor`;
  2º fator (TOTP) obrigatório para administradores.
- Isolamento por inquilino aplicado em todas as consultas (dependência FastAPI que injeta o filtro).
- Paginação padronizada em todas as listagens: `page`, `size`, `sort`, `filter`.
- Traefik como gateway com TLS.
- Contratos publicados em URL pública com histórico de versões.
- Adaptador plugável de exemplo (contêiner que converte um JSON próprio para o canônico).
- `/metrics` em formato Prometheus em cada serviço; logs JSON com `correlation_id = id_mensagem`.
- Painel básico no Grafana: mensagens/s, latência, último estado, alarmes ativos.

### Fase 2 — Integração (requisitos "Importante")

| Tema | Requisitos | Entrega principal |
|---|---|---|
| Gêmeo e comandos | RF-DIS-04, RF-DIS-05 | Semáforo recebe `wait`/`crossing` via `PUT .../gemeo/desejado`; diferença entregue na reconexão |
| Regras e config na borda | RF-EDG-03, RF-EDG-04, RF-EDG-05 | Regra de irrigação dispara offline; alarmes priorizados no sync |
| Gestão da borda | RF-EDG-06, RF-OBS-04, RF-OBS-05 | Painel "há quanto tempo cada nó está sem sincronizar" + alerta |
| Geometrias | RF-CEN-04 | PostGIS; área de espera do semáforo como polígono GeoJSON |
| NGSI-LD | RF-CEN-06, RF-INT-05 | Orion-LD com `TrafficFlowObserved` e `AgriParcel` |
| Agregações e retenção | RF-PRO-04, RF-DAD-03 | Continuous aggregates do TimescaleDB |
| Notificações | RF-APP-03, RF-APP-05 | Webhooks com retry; Telegram, e-mail e ntfy; SMS opcional |
| Tempo real e painéis | RF-APP-02, RF-APP-04, RF-APP-06 | WebSocket da plataforma; mapa de bairros/talhões |
| Kit do integrador | RF-INT-04, RF-INT-06, RF-INT-07 | Sandbox, validador, guia e coleção de requisições |
| Demais | RF-ING-05, RF-ING-07, RF-ING-10, RF-DIS-03, RF-DIS-07, RF-DAD-04, RF-DAD-06, RF-SEG-06, RF-OBS-03 | LoRaWAN, CBOR, rate limit, provisionamento em lote, tags, exportação, auditoria, chaves de API, tracing |

### Fase 3 — Evolução (requisitos "Desejável")

RF-CEN-05 (modelos de cenário), RF-EDG-07 (painel local da borda), RF-ING-09 (CoAP), RF-DIS-08 (OTA com grupo
canário), RF-PRO-06 (funções externas), RF-INT-08 (mapeamento de campos sem código), k3s + Helm para escala.

---

## 6. Critérios de aceite do MVP

Cada critério da seção 9.3 do documento vira um teste automatizado ou roteiro de demonstração:

| Critério | Como será verificado |
|---|---|
| Um projeto urbano e um rural integrados; o rural com nó de borda | Demo: semáforo → central; `soil-sensor-sim` → borda → central |
| Desconexão de 72 h sem perda nem duplicação | Teste automatizado com relógio simulado + `docker network disconnect`; contagem origem = destino |
| Domínio novo só por configuração (RNF-08) | Script cria `recursos_hidricos` e perfil via API; sensor publica e aparece no histórico (UC-06) |
| Integração em 3 linguagens | `projects/examples/` em Python, Node.js e Go publicando com bibliotecas genéricas |
| RNF-01 e RNF-02 | Locust: 1.000 msg/s sustentadas; p95 ingestão → persistência ≤ 2 s; regra ≤ 3 s |

---

## 7. Rastreabilidade de requisitos

Requisitos "Essencial" (Fase 1) e onde são atendidos:

| Módulo | Requisitos | Item do roteiro |
|---|---|---|
| CEN | 01, 02, 03 | 1.1 |
| ING | 01, 02, 03, 04, 06, 08 | 1.2 |
| EDG | 01, 02 | 1.5 |
| DIS | 01, 02, 06 | 1.1 |
| INT | 01, 02, 03 | 0.3, 0.4, 1.4, 1.6 |
| PRO | 01, 02, 03, 05 | 1.3 |
| DAD | 01, 02, 05 | 1.3, 1.4 |
| APP | 01, 07 | 1.6 |
| SEG | 01, 02, 03, 04, 05 | 1.1, 1.5, 1.6 |
| OBS | 01, 02 | 1.6 |

Requisitos não funcionais com atenção especial no MVP: RNF-04, RNF-07, RNF-08, RNF-10, RNF-13, RNF-14, RNF-15
(cobertura ≥ 70% no núcleo, verificada no CI).

---

## 8. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Escopo "Essencial" grande para a equipe | Atraso no MVP | Priorizar o fluxo vertical semáforo → ingestão → banco → API, depois borda; Keycloak pode começar como JWT simples (registrar em ADR) |
| Stack pesada para uma máquina só | Lentidão em notebooks | Perfis do Compose (`--profile core`, `--profile obs`); Valkey e Orion-LD só quando necessários |
| Teste de 72 h inviável em tempo real | Critério não demonstrado | Relógio injetável no domínio + teste acelerado; uma execução longa real antes da entrega |
| Quebra do semáforo durante a refatoração | Perda da demo atual | Fase 0 sem mudança de lógica; testes atuais como rede de segurança |
| SMS com custo | RF-APP-05 parcial | Telegram/ntfy + ADR; SMS via gateway Android opcional |
| Licenças mudando (BSL, SSPL) | Custo ou restrição futura | ADR-000 + `pip-audit` e revisão de licença ao adicionar dependências |

---

## 9. ADRs previstos

| ADR | Decisão |
|---|---|
| ADR-000 | Somente componentes gratuitos e de código aberto (tabela da seção 2) |
| ADR-001 | Monorepo com plataforma e projetos integrados |
| ADR-002 | NATS JetStream como barramento interno |
| ADR-003 | PostgreSQL + TimescaleDB como armazenamento central; SQLite na borda |
| ADR-004 | Python/FastAPI para os serviços; arquitetura hexagonal |
| ADR-005 | Contrato canônico v1.0 e convenção de tópicos |
| ADR-006 | Notificações: Telegram/e-mail/ntfy no lugar de SMS pago |

Formato: contexto, alternativas consideradas, decisão e consequências.

---

## 10. Próximos passos

1. Confirmar a premissa de escopo (monorepo da plataforma × apenas integrar o semáforo).
2. Executar a Fase 0, itens 0.1 e 0.2 (reestruturação + ADRs).
3. Escrever o JSON Schema canônico com testes de validação (0.3).
4. Implementar o `MqttPublisher` do semáforo e subir o Mosquitto via Compose (início do 1.4) — primeira demo
   visível: o semáforo publicando no formato canônico.
