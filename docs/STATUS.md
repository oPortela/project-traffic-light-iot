# Status atual do roadmap


O escopo foi ampliado pelo usuário para avançar sequencialmente até o fim do roadmap.
As seções ao final são registro das entregas históricas, não o status atual.

| Item | Estado atual | Evidência |
|---|---|---|
| 0, 1.1, 1.4 | Implementados | Fundação, cadastro e semáforo MQTT |
| 1.2 | Implementado e validado localmente | HTTP e MQTT reais → JetStream → Timescale; reenvio não duplicou leitura |
| 1.3 | Implementado e validado localmente | Histórico, último estado, três regras, alarmes e ações duráveis; smoke integrado passou |
| 1.5 | Implementado e validado localmente | SQLite WAL cifrado, confirmação de aplicação após commit, sync por item; smoke rural e 72 h simuladas passaram |
| 1.6 | Implementado; painéis ainda em validação | Keycloak real + TLS + token OIDC/RBAC passaram; contratos em /contratos/v1; adaptador legado e métricas criados |
| 2 | Em implementação | Gêmeo desejado/relatado com reenvio testado; agregações/retenção validadas com rollback; exemplos em três linguagens |
| 3 | Pendente | Ainda não declarar finalização do roadmap |

Última regressão: 72 testes passaram, 78,15% de cobertura. Auditorias da plataforma
e borda não encontraram vulnerabilidades conhecidas. Retenção automática não foi
ativada: a revisão automática bloqueou exclusão futura; o SQL foi validado em uma
transação com rollback, sem deixar políticas destrutivas ativas.
Nenhuma medição de 1.000 mensagens/s ou ensaio físico de 72 horas
foi concluído. Guia: [ingestão e borda](integrador/ingestao-e-borda.md).


---

## Historico das entregas anteriores

# Status das entregas

## Etapa atual — cadastro (1.1)

Implementados: catálogo de domínios, perfis com grandezas/unidades/faixas/intervalos,
hierarquia inquilino → site → área → dispositivo, persistência PostgreSQL, tokens por
dispositivo, revogação, listagens paginadas, cálculo de status por perfil e geração de ACLs.
Domínios e perfis iniciais são dados em JSON, sem ramificações por domínio no núcleo.

Validação: **51 testes passaram, 97,28% de cobertura no núcleo configurado**; lint e ambos
os contratos OpenAPI validados; auditoria do registry sem vulnerabilidades conhecidas.
O broker real aceitou o hash exportado, negou tópicos alheios/publicação de comandos e
recusou a credencial revogada após exportação e reinício. API e PostgreSQL iniciaram saudáveis.

Limites explícitos: autenticação administrativa local por token, até o Keycloak (1.6);
unidades UCUM limitadas ao catálogo configurável; heartbeat autenticado para o status,
até a integração com ingestão (1.2); revogação MQTT exige exportação e reinício administrativo.
CI atualizado com banco e smoke test; execução no GitHub depende de push.

Guia: [cadastro e credenciais](integrador/cadastro.md). Decisão: [ADR-007](adr/ADR-007-registry.md).
**Próxima etapa: 1.2 — ingestão MQTT/HTTP/lote, validação, deduplicação e publicação no NATS.**

## Histórico — primeira entrega

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

Na primeira entrega, PostgreSQL e NATS foram apenas provisionados. O catálogo foi entregue
na etapa 1.1 acima; persistência de telemetria, regras, borda, Keycloak e fases 2/3 permanecem pendentes.

Instruções completas: [primeira demonstração](integrador/primeira-demo.md).
