# ADR-002 — NATS JetStream

Status: infraestrutura definida; consumidores pendentes na fase 1.

## Contexto
A ingestão deve desacoplar armazenamento, regras e tempo real.

## Alternativas consideradas
Chamadas síncronas, Kafka, Redis Streams e NATS JetStream.

## Decisão
Provisionar NATS com JetStream e volume persistente apenas na rede interna do Compose.
Nesta entrega o semáforo publica no Mosquitto; nenhum stream NATS é criado e nenhuma
mensagem é encaminhada ao banco.

## Consequências
Na fase 1 será necessário definir streams, retenção, ACK após persistência,
autenticação interna e idempotência dos consumidores.
