# Status da primeira entrega

Escopo confirmado: **fundação + semáforo MQTT**, conforme fases 0 e 1.4 do roadmap.
O roadmap original está preservado em `docs/ROADMAP.md`; os itens futuros não são
marcados como entregues por terem apenas infraestrutura provisionada.

| Item | Implementação | Evidência / limite |
|---|---|---|
| 0.1 Monorepo | Concluída | app/static/tests em projects/traffic-light; Controller preservado |
| 0.2 ADR-000 a 004 | Escritos, mais ADR-005 | Revisão humana pela equipe ainda pendente |
| 0.3 JSON Schema | Concluído com exemplos e rejeições | Contrato provisório; Documento de Requisitos v2.0 não fornecido |
| 0.4 AsyncAPI | Quatro tópicos, QoS e identidade | Validação pelo CLI oficial |
| 0.5 Compose | Mosquitto, TimescaleDB/PostgreSQL, NATS e demo opcional | Todos iniciaram saudáveis na validação local |
| 0.6 CI | pytest/cobertura, Ruff, contratos, auditoria e smoke MQTT | Checks locais executados; execução no GitHub depende de push |
| 0.7 pytest | Migração dos dez casos originais e novos casos | 33 testes passaram; 98% no núcleo configurado |
| 1.4 Semáforo MQTT | Publicador, comandos, eventos e estado | Smoke com Mosquitto real passou |

## Validação executada

- `pytest --cov --cov-report=term-missing`: 33 testes passaram; Controller e contratos
  com 100%, adaptador com 96%, agregado de 98%. A cobertura configurada mede o núcleo,
  não o processamento de câmera. Há um aviso de depreciação do TestClient/httpx.
- `ruff check .`: sem erros.
- `scripts/validate_contracts.py`: schema, dois exemplos e OpenAPI conferidos.
- AsyncAPI CLI: contrato validado; avisos de metadados/licença não declarada pelo projeto
  e recomendação de versão mais recente não impedem a validação.
- `pip-audit -r requirements-core.txt`: nenhuma vulnerabilidade conhecida na consulta.
- Compose com projeto isolado `iot-roadmap-validation`: quatro serviços saudáveis.
- `scripts/smoke_mqtt.py`: telemetria, evento, estado, configuração remota, start/stop e
  rejeição de reentrega do mesmo comando verificados entre o cliente e o contêiner real.

## Limites e próxima entrega

O dashboard e os endpoints locais continuam funcionando. Sem `MQTT_HOST`, não há
dependência de broker em execução. A câmera foi preservada, mas não testada com hardware
nesta entrega. O Dockerfile é para modo demonstração e não inclui YOLO/OpenCV.

A fila Paho é volátil e limitada a 1000 mensagens; não fornece a garantia de 72 h da
borda. A deduplicação de comandos é volátil e não garante execução única após reinício.
O estado retido representa o último relato, não comprova conexão atual. TLS externo,
identidade central e isolamento multi-inquilino da API pertencem ao MVP da plataforma.

PostgreSQL e NATS foram provisionados, mas não estão conectados à ingestão. Catálogo,
persistência de telemetria, regras, borda, Keycloak e fases 2/3 permanecem pendentes.
O próximo passo é o fluxo vertical cadastro → ingestão MQTT/HTTP → NATS → armazenamento → API.

Instruções completas: [primeira demonstração](integrador/primeira-demo.md).
