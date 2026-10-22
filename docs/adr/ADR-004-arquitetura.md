# ADR-004 — Python e domínio separado do protocolo

Status: adotado; revisão da equipe pendente.

## Contexto
O Controller existente implementa RN01–RN05 usando relógio monotônico.

## Alternativas consideradas
Adicionar MQTT ao Controller, reescrever o domínio ou usar adaptadores externos.

## Decisão
Preservar o Controller sem alterações. `TrafficIntegration` mapeia snapshots e transições
para envelopes; `EventPublisher` abstrai o transporte e `MqttPublisher` implementa MQTT.
Converter monotônico para UTC apenas nessa fronteira. Comandos reutilizam os validadores
e bloqueios da API local. Sem `MQTT_HOST`, o modo standalone não importa o adaptador MQTT.

## Consequências
Falhas de rede não bloqueiam o domínio. Testes usam publicador em memória e cliente MQTT
substituto. O domínio continua testável sem câmera, broker ou rede.
