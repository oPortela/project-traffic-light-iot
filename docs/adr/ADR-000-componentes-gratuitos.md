# ADR-000 — Componentes gratuitos

Status: adotado na implementação; revisão da equipe pendente.

## Contexto
O projeto acadêmico deve executar localmente sem contratar serviços pagos.

## Alternativas consideradas
Serviços SaaS, componentes BSL e componentes auto-hospedados.

## Decisão
Conferir licença e custo antes de adicionar dependências. Esta entrega acrescenta
Paho MQTT (EPL-2.0 ou EDL-1.0) e jsonschema (MIT). Ferramentas: pytest/pytest-cov (MIT),
Ruff (MIT), PyYAML (MIT), pip-audit (Apache-2.0), AsyncAPI CLI (Apache-2.0).
Mosquitto usa EPL/EDL; NATS, Apache-2.0; PostgreSQL, PostgreSQL License.
TimescaleDB inclui Apache-2.0 e Timescale License: é gratuito auto-hospedado, mas **não
é integralmente open source** sob critérios OSI. O uso existente de Ultralytics continua AGPL-3.0.

Fontes de revisão:
- https://github.com/eclipse-paho/paho.mqtt.python/blob/master/LICENSE.txt
- https://github.com/python-jsonschema/jsonschema/blob/main/pyproject.toml
- https://github.com/timescale/timescaledb/blob/main/LICENSE
- https://github.com/pytest-dev/pytest/blob/main/LICENSE
- https://github.com/pytest-dev/pytest-cov/blob/master/LICENSE
- https://github.com/astral-sh/ruff/blob/main/LICENSE
- https://github.com/pypa/pip-audit/blob/main/LICENSE
- https://github.com/yaml/pyyaml/blob/main/LICENSE
- https://github.com/asyncapi/cli/blob/master/LICENSE

## Consequências
Sem cobrança de licença na execução local. Atualizações exigem revisão; `pip-audit`
detecta vulnerabilidades, não verifica licença ou custo. Não oferecer TimescaleDB como
serviço comercial gerenciado sem revisar a licença. Revisar dependências transitivas antes de distribuir.
