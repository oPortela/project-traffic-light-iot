# ADR-008 — Ingestão e sincronização duráveis

## Decisão

O HTTP confirma após commit no PostgreSQL. A outbox publica no JetStream; o consumidor
confirma após persistir histórico, estado e alarmes na mesma transação. Reenvios com
o mesmo identificador e conteúdo são idempotentes. Reutilização com outro conteúdo
é conflito. Leituras atrasadas permanecem no histórico, sem gerar alarmes atuais.

A borda usa SQLite WAL, synchronous=FULL e cifra autenticada Fernet por registro.
A chave fica em secret separado. A sincronização só apaga itens individualmente
confirmados pela central; rejeições permanentes ficam em quarentena cifrada.

`cryptography` é gratuito e disponibilizado sob Apache-2.0 ou BSD, conforme a
[licença oficial](https://github.com/pyca/cryptography/blob/main/LICENSE).
`nats-py` usa Apache-2.0, conforme a
[licença oficial](https://github.com/nats-io/nats.py/blob/main/LICENSE).

## Consequências

A entrega é pelo menos uma vez, com efeitos idempotentes na central. Webhooks devem
honrar Idempotency-Key. A chave de cifra deve ser preservada junto ao backup da fila;
perdê-la torna os registros irrecuperáveis. Campos de estado/evento são enumerados
no perfil: texto livre, imagens e objetos arbitrários não são aceitos.

As credenciais locais de administração continuam sendo bootstrap, não substituem
o OIDC/RBAC previsto no item 1.6. O teste acelerado de desconexão não substitui um
ensaio de campo de 72 horas nem o ensaio de carga de 1.000 mensagens/s.
