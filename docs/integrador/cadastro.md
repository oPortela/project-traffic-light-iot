# Cadastro — etapa 1.1

Esta entrega implementa domínios, perfis, sites, áreas, dispositivos, credenciais e status
persistentes. A ingestão de telemetria será a próxima etapa (1.2).

## Inicialização

Na raiz do projeto, com Docker Desktop em modo Linux:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
.\.venv\Scripts\python.exe scripts/init_registry.py --tenant semob --tenant fazenda
```

O arquivo `deploy/secrets/registry-admins.json` contém tokens administrativos e não entra
no Git. O script recusa sobrescrever um arquivo existente. Proteja o acesso a esse arquivo;
ele deve ser legível pelo usuário do contêiner. A configuração local substitui Keycloak
apenas nesta etapa. Cada token permite administrar um único inquilino.

Se ainda não existir, copie `deploy/.env.example` para `deploy/.env` e preencha as senhas.
Não sobrescreva seu `.env` já configurado na primeira entrega.

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml --profile registry up -d --build --wait registry
```

Esse comando inicia somente o cadastro e sua dependência PostgreSQL. API e Swagger:
http://127.0.0.1:8001/docs. No botão **Authorize**, informe o token do inquilino desejado.
O schema é aplicado transacionalmente, com bloqueio contra inicializações concorrentes,
em bancos novos ou existentes. Não é preciso remover o volume da primeira entrega.

## Criar locais e dispositivo

```powershell
$admin = (Get-Content deploy/secrets/registry-admins.json -Raw | ConvertFrom-Json | Where-Object inquilino -eq semob).token
$headers = @{ Authorization = "Bearer $admin" }
$base = 'http://127.0.0.1:8001/api/v1'
Invoke-RestMethod -Method Post -Uri "$base/sites" -Headers $headers -ContentType 'application/json' -Body '{"id":"centro","nome":"Centro"}'
Invoke-RestMethod -Method Post -Uri "$base/sites/centro/areas" -Headers $headers -ContentType 'application/json' -Body '{"id":"praca","nome":"Praca"}'
$device = Invoke-RestMethod -Method Post -Uri "$base/dispositivos" -Headers $headers -ContentType 'application/json' -Body '{"id":"semaforo-travessia-01","nome":"Travessia","site":"centro","area":"praca","perfil":"semaforo-v1"}'
```

Guarde `$device.credencial.usuario` e `$device.credencial.token` em um gerenciador de
segredos ou configuração local protegida. **O token não aparece novamente nas consultas.**
Não imprima ou publique a resposta em logs. IDs duplicados no mesmo contexto retornam 409;
referências fora do inquilino/local ou inválidas retornam 422.

Os perfis iniciais são `semaforo-v1` (5 s, tolerância de 3 intervalos) e
`solo-horario-v1` (3600 s, tolerância de 3 intervalos). Todos os inquilinos recebem os
domínios e perfis de `platform/registry/seed.json`. O seed é idempotente e não altera
objetos existentes. `REGISTRY_SEED_FILE` permite escolher outro JSON no serviço.

## Novo domínio por configuração

```powershell
Invoke-RestMethod -Method Post -Uri "$base/catalogo/dominios" -Headers $headers -ContentType 'application/json' -Body '{"id":"recursos_hidricos","nome":"Agua"}'
Invoke-RestMethod -Method Post -Uri "$base/perfis" -Headers $headers -ContentType 'application/json' -Body '{"id":"nivel-v1","nome":"Nivel","dominio":"recursos_hidricos","intervalo_esperado_s":900,"tolerancia_intervalos":3,"grandezas":{"nivel":{"unidade":"m","minimo":0,"maximo":20}}}'
```

Não há condição por nome de domínio no código. As unidades aceitas são códigos do
catálogo UCUM configurado no seed; amplie esse catálogo com códigos UCUM revisados para
novas grandezas. O serviço não implementa conversão de unidades.

## Consultas e status

Listagens usam `page`, `size` (até 200), `sort` (`id`, `-id`, `nome`, `-nome`) e `filter`
(trecho literal do nome, sem distinção de maiúsculas). Exemplo:

```powershell
Invoke-RestMethod -Uri "$base/dispositivos?page=1&size=20&sort=nome" -Headers $headers
$deviceHeaders = @{ Authorization = "Bearer $($device.credencial.token)" }
Invoke-RestMethod -Method Post -Uri "$base/dispositivos/semaforo-travessia-01/heartbeat?inquilino=semob" -Headers $deviceHeaders
```

O heartbeat autentica o token do dispositivo e usa o horário UTC da central. O status é
online até `intervalo_esperado_s × tolerancia_intervalos` desde o último contato; antes
do primeiro contato, ou após revogação, é offline. Um sensor horário não é considerado
offline depois de cinco minutos. Nesta etapa, mensagens MQTT não substituem o heartbeat;
essa conexão será implementada na ingestão.

## Aplicar credenciais e ACL no Mosquitto

O broker de cadastro usa **1884**, separado da demo estática anterior em 1883.

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml --profile registry exec --user root registry python -m registry_service.broker --output /mosquitto-export
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml --profile registry-mqtt up -d --wait registry-mosquitto
```

Use as credenciais retornadas pelo cadastro para conectar o semáforo local:

```powershell
$env:MQTT_HOST = 'localhost'
$env:MQTT_PORT = '1884'
$env:MQTT_USERNAME = $device.credencial.usuario
$env:MQTT_PASSWORD = $device.credencial.token
$env:IOT_INQUILINO = 'semob'
$env:IOT_SITE = 'centro'
$env:IOT_DOMINIO = 'mobilidade'
$env:IOT_DISPOSITIVO = 'semaforo-travessia-01'
.\iniciar.bat
```

Cada dispositivo só publica telemetria/evento/estado no próprio caminho e lê seu comando.
Não há usuário operador global neste broker: o adaptador central de comandos virá depois.
O `mqtt_cli.py listen` da primeira demo usa uma credencial privilegiada do broker antigo,
portanto não se aplica a este broker.

## Revogar

```powershell
Invoke-RestMethod -Method Delete -Uri "$base/dispositivos/semaforo-travessia-01/credenciais" -Headers $headers
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml --profile registry exec --user root registry python -m registry_service.broker --output /mosquitto-export
docker compose --env-file deploy/.env -f deploy/docker-compose.yml -f deploy/docker-compose.registry.yml --profile registry-mqtt restart registry-mosquitto
```

A API revoga imediatamente o acesso HTTP. **No MQTT, a revogação só estará aplicada após
exportar e reiniciar o broker**, encerrando também sessões antigas. A resposta informa
`mqtt_aplicacao_pendente: true`. Para novos cadastros depois da primeira exportação,
repita exportação e reinício. Execuções concorrentes do exportador não são suportadas;
serialize o procedimento administrativo. Gerações antigas permanecem disponíveis para
auditoria local e não devem ser restauradas após revogações.

## Testar

Use um PostgreSQL descartável e configure `TEST_REGISTRY_DATABASE_URL`. A suíte cria
inquilinos aleatórios e remove apenas os dados desses inquilinos. Exemplo de URL:
`postgresql://iot:SENHA@127.0.0.1:5432/registry_test`.

O overlay `deploy/docker-compose.registry-test.yml` expõe PostgreSQL em `127.0.0.1:15433`
para testes locais. Use-o apenas com um projeto Compose descartável e ajuste a variável
`TEST_REGISTRY_DATABASE_URL` para essa porta e o banco escolhido.

```powershell
.\.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts/validate_contracts.py
```

Sem a variável de teste, casos de integração PostgreSQL são ignorados. No CI, o banco
descartável é obrigatório. Contrato versionado: `contracts/registry-openapi.yaml`.
