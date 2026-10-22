# Primeira entrega: fundação + semáforo MQTT

Execute os comandos na raiz do repositório, em PowerShell, com Python 3.12 e Docker
Desktop usando contêineres Linux. O dashboard standalone também funciona sem Docker.

## 1. Preparar o ambiente

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev-lock.txt
```

Para câmera, instale também `requirements.txt` (YOLO/OpenCV). O contêiner desta entrega
inclui apenas modo demonstração. O arquivo antigo `requirements-lock.txt` preserva o
ambiente de visão original; ele não inclui as dependências novas de MQTT.

## 2. Executar sem broker

```powershell
Remove-Item Env:MQTT_HOST -ErrorAction SilentlyContinue
.\iniciar.bat
```

Abra http://127.0.0.1:8000. Simule presença e confira a sequência original. Não use
múltiplos workers, pois câmera e controlador compartilham estado no processo.

## 3. Criar credenciais do broker

Copie `deploy/.env.example` para `deploy/.env` e preencha `POSTGRES_PASSWORD` e
`MQTT_PASSWORD` com senhas locais. Não versione esse arquivo. `MQTT_PASSWORD` deve ser
a mesma senha informada abaixo para `semob-centro-semaforo-01`.

```powershell
Copy-Item deploy/.env.example deploy/.env
docker run --rm -it -v "${PWD}/deploy/secrets:/secrets" eclipse-mosquitto:2.0 mosquitto_passwd -c /secrets/mosquitto.passwd semob-centro-semaforo-01
docker run --rm -it -v "${PWD}/deploy/secrets:/secrets" eclipse-mosquitto:2.0 mosquitto_passwd /secrets/mosquitto.passwd plataforma
docker run --rm -v "${PWD}/deploy/secrets:/secrets" eclipse-mosquitto:2.0 chmod 644 /secrets/mosquitto.passwd
```

Use uma senha diferente para `plataforma`. O arquivo contém hashes, é ignorado pelo Git
e precisa ser legível pelo usuário do Mosquitto no contêiner. Não repita `-c` ao adicionar
usuários, pois essa opção substitui o arquivo. A ACL permite ao semáforo escrever apenas
seus três tópicos de saída e ler seu tópico de comando. `plataforma` é a credencial
privilegiada de integração da demo; não deve ser distribuída a dispositivos.

## 4. Subir a infraestrutura

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml config --quiet
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --wait
```

Isso inicia Mosquitto, PostgreSQL/TimescaleDB e NATS JetStream. Os dois últimos ficam
preparados para a fase 1; **ainda não recebem dados do semáforo**. O schema SQL inicial
é aplicado somente na criação do volume PostgreSQL. Não remova volumes para atualizar
um banco que contenha dados.

## 5. Conectar o semáforo

Opção A, aplicação local (a senha é a do dispositivo):

```powershell
$env:MQTT_HOST = 'localhost'
$env:MQTT_USERNAME = 'semob-centro-semaforo-01'
$env:MQTT_PASSWORD = Read-Host 'Senha MQTT do dispositivo'
.\iniciar.bat
```

Opção B, modo demonstração no Compose (encerre o servidor local antes):

```powershell
docker compose --env-file deploy/.env -f deploy/docker-compose.yml --profile demo up -d --build --wait
```

## 6. Observar e comandar

Em outro terminal, com a credencial `plataforma`:

```powershell
$env:MQTT_HOST = 'localhost'
$env:MQTT_USERNAME = 'plataforma'
$env:MQTT_PASSWORD = Read-Host 'Senha MQTT da plataforma'
.\.venv\Scripts\python.exe projects/examples/python/mqtt_cli.py listen
```

No dashboard, inicie a simulação e ative presença. Confira:

| Tópico após `semob/centro/mobilidade/semaforo-travessia-01/` | Resultado |
|---|---|
| `telemetria` | Contagem, espera em segundos e ciclos a cada 5 s |
| `evento` | Origem e destino de cada transição da máquina de estados |
| `estado` | wait, crossing, roi, modo e running ao iniciar, mudar e reconectar |

Interrompa o listener com Ctrl+C para enviar um comando:

```powershell
.\.venv\Scripts\python.exe projects/examples/python/mqtt_cli.py stop
.\.venv\Scripts\python.exe projects/examples/python/mqtt_cli.py config --params '{"wait": 5, "crossing": 8, "roi": [0.2, 0.15, 0.8, 0.95]}'
.\.venv\Scripts\python.exe projects/examples/python/mqtt_cli.py start
.\.venv\Scripts\python.exe projects/examples/python/mqtt_cli.py reset
```

`config` só é aceito com a simulação parada. `start` aceita `{"mode":"demo"}` ou
`{"mode":"camera"}` em `--params`; a câmera exige execução local com dependências de visão.
O CLI gera UUID e timestamp novos: o JSON de exemplo estático não serve para reenviar
comandos atuais. A confirmação do broker não significa execução; confira o estado e logs.

## 7. Verificação e encerramento

```powershell
.\.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts/validate_contracts.py
docker compose --env-file deploy/.env -f deploy/docker-compose.yml --profile demo down
```

`down` preserva volumes. A fila MQTT do semáforo mantém até 1000 mensagens em memória,
com reconexão automática e QoS 1; não substitui a fila durável da futura borda. Mensagens
podem se perder após encerramento ou saturação. O estado retido é o último relato,
não um indicador de conexão atual. Comandos têm validade de 5 minutos e deduplicação
volátil de 1024 IDs. O broker local é limitado ao loopback do host; TLS externo não está
configurado neste Compose. Para broker externo com TLS, configure `MQTT_CA_CERT` e
`MQTT_PORT`; não desabilite verificação do certificado.

Identidade alternativa usa `IOT_INQUILINO`, `IOT_SITE`, `IOT_DOMINIO`, `IOT_DISPOSITIVO`
e opcionalmente `MQTT_CLIENT_ID`. Atualize também cadastro manual/ACL/credenciais.
O contrato provisório depende de revisão contra o Documento de Requisitos v2.0.
