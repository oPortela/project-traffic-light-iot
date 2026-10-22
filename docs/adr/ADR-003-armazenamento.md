# ADR-003 — Armazenamento central e borda

Status: infraestrutura central definida; escritor central e borda pendentes.

## Contexto
São necessárias séries temporais na central e recuperação após perda de link na borda.

## Alternativas consideradas
PostgreSQL puro, TimescaleDB e bancos proprietários; SQLite ou arquivos na borda.

## Decisão
Provisionar PostgreSQL/TimescaleDB com volume e SQL inicial. Separar a chave de
deduplicação da hypertable, cuja unicidade deve incluir a coluna de tempo.
Manter último estado em tabela própria. SQLite WAL com cifra por registro é a decisão
para a fase 1.5, sem implementação nesta entrega.

## Consequências
A aplicação standalone continua sem persistência. A fila Paho é limitada e em memória;
não há garantia de armazenamento durável no semáforo. A garantia de 72 h será implementada
e demonstrada pela borda. SQL inicial roda somente com volume PostgreSQL novo.
