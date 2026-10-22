# Ingestão, regras e borda

## Central

Cadastre locais e dispositivos conforme [cadastro](cadastro.md). Para uma instalação
existente, execute `python scripts/init_registry.py --services-only` para adicionar
os segredos dos serviços sem trocar credenciais existentes.

Defina `POSTGRES_PASSWORD` e `MQTT_PASSWORD` conforme a instalação. Use os três arquivos:

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml -f deploy/docker-compose.platform.yml --profile registry --profile platform up -d --build registry ingestion outbox data-api storage-writer rules-worker
```

A API de ingestão escuta em `127.0.0.1:8002`; dados/regras em `127.0.0.1:8003`.
`POST /api/v1/ingestao` recebe um envelope com Bearer do dispositivo.
`POST /api/v1/ingestao/lote` recebe `{"mensagens": [...]}`, até 5.000 itens.
Cada resultado contém `indice`, `status` e, nas rejeições, `http_status` e `erros`.
202 significa commit na caixa de entrada durável; o histórico é atualizado de forma
assíncrona. Consulte os contratos em `/docs` e `contracts/*-openapi.yaml`.

Para MQTT, exporte as credenciais e inicie o broker/bridge:

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml -f deploy/docker-compose.platform.yml --profile registry exec registry python -m registry_service.broker --output /mosquitto-export
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml -f deploy/docker-compose.platform.yml --profile registry --profile platform --profile registry-mqtt --profile platform-mqtt up -d --build registry-mosquitto mqtt-bridge
```

Após revogar uma credencial, repita a exportação e reinicie `registry-mosquitto`.
O bridge só pode ler telemetria/eventos/estados; o executor de ações só pode publicar
comandos e tópicos `acoes/{inquilino}/{dispositivo}/...`.

## Consultas e regras

Use Bearer administrativo do inquilino em:

- `GET /api/v1/telemetria`: filtros dispositivo, grandeza, inicio, fim, page e size.
- `GET /api/v1/dispositivos/{id}/ultimo-estado`.
- `GET /api/v1/ingestao/rejeitadas`: motivos e hash; payload inválido não é armazenado.
- `POST /api/v1/regras`: tipos `limite`, `ausencia` e `janela` (média temporal).
- `GET /api/v1/alarmes` e `POST /api/v1/alarmes/{id}/reconhecer`.
- `GET /api/v1/acoes`: entregas, tentativas e último tipo de erro.

Exemplo de regra:

```json
{"id":"solo-seco","dispositivo":"solo-01","tipo":"limite","grandeza":"umidade_solo","operador":"lt","limite":30,"severidade":"aviso","acoes":[{"tipo":"alarme"}]}
```

Ações adicionais: `webhook` (destino deve pertencer a `WEBHOOK_ALLOWED_HOSTS`),
`topico` (restrito ao dispositivo) e `comando` (dados canônicos com acao/parametros).
Há até 15 tentativas, com backoff até 300 s. Webhooks recebem Idempotency-Key e devem
ser idempotentes. Dados atrasados/suspeitos ficam no histórico, sem alarmes atuais.

Perfis definem `campos.estado` e `campos.evento` por tipos numero, booleano, enum ou
vetor numérico limitado. Campos desconhecidos são rejeitados. Ao migrar perfis antigos,
crie uma nova versão com esses campos e provisione o dispositivo com esse perfil;
o seed não sobrescreve configurações existentes.

## Borda rural

Cadastre um dispositivo com `solo-horario-v1` e salve a resposta de criação
(contém segredo) em `deploy/secrets/solo-device.json`. Execute:

```powershell
python scripts/init_edge.py --device-file deploy/secrets/solo-device.json
docker compose -p iot-edge -f deploy/docker-compose.edge.yml --profile soil-demo up -d --build
```

O simulador publica a cada hora; `SOIL_INTERVAL_S` permite acelerar demonstrações.
O broker local escuta em `127.0.0.1:1885`. A central padrão é
`http://host.docker.internal:8002`; use `--central` para outro endereço.
Em redes externas, configure HTTPS válido. Não use verificação TLS desabilitada.

SQLite usa WAL e synchronous=FULL. A confirmação de aplicação em
`.../confirmacao` ocorre após commit; o simulador aguarda essa confirmação e reenvia
o mesmo identificador se ela não chegar. O PUBACK do broker sozinho não prova a
persistência na fila. A confirmação da assinatura do bridge também ocorre após commit. A fila contém
cifra autenticada por registro; a chave `edge.key` deve ser preservada separadamente.
Não execute novamente o bootstrap para rotacionar uma chave de fila existente.
Um lote pode confirmar parte das mensagens; somente essas são removidas. Erros
400/409/422 por item vão para quarentena cifrada; falhas de rede/autenticação retentam.
A fila não descarta dados quando cheia: interrompe a confirmação ao broker.

## Verificação

`scripts/smoke_platform.py`, com `REGISTRY_ADMINS_FILE`, verifica a central real.
Os testes em `edge/tests` simulam 72 horas e confirmação perdida. Isso não substitui
ensaio de campo de 72 horas, falha elétrica do hardware ou teste sustentado de carga.
