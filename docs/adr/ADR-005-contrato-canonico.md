# ADR-005 — Contrato canônico v1.0

Status: contrato provisório implementado; comparação com Requisitos v2.0 pendente.

## Contexto
O roadmap cita um Documento de Requisitos v2.0 não fornecido. Não é possível afirmar
compatibilidade com seu exemplo original da seção 4.4.

## Alternativas consideradas
Bloquear a primeira entrega ou explicitar um contrato provisório verificável.

## Decisão
JSON Schema draft-07 (compatível com o parser do AsyncAPI CLI): UUID, UTC com sufixo Z, versão, identidade, tipo e dados.
Grandezas têm valor numérico e unidade UCUM. Tópicos usam a identidade do envelope.
QoS 1 admite duplicação; estado é retido e comandos nunca são retidos. Rejeitar comandos
com mais de 5 min, mais de 30 s no futuro, identidade incompatível e IDs repetidos no
cache dos últimos 1024. O cache é volátil, sem garantia após reinício.

## Consequências
O schema não conhece `mobilidade`; novos domínios usam o mesmo envelope. O semáforo
só envia agregados/configuração, sem imagens, IDs de rastreamento ou caixas.
O relógio deve estar sincronizado. Recusas de comandos são registradas em log; ACK de
execução e gêmeo desejado ficam para a fase 2. O OpenAPI descreve apenas a API local existente.
