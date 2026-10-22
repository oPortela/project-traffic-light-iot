# ADR-007 — Cadastro persistente e credenciais locais

Status: implementado para o item 1.1; revisão da equipe pendente.

## Contexto
A primeira entrega publica MQTT, mas não possui cadastro central de perfis, locais
ou credenciais. O item 1.6 entregará Keycloak; o cadastro precisa de autenticação agora.

## Alternativas consideradas
API sem autenticação, JWT provisório ou tokens opacos vinculados a inquilinos; SQLite
temporário ou PostgreSQL desde o início; alterações no broker via Docker socket ou
exportação administrativa de arquivos.

## Decisão
Usar PostgreSQL com chaves compostas incluindo o inquilino em todas as referências.
O adaptador usa Psycopg 3 (LGPL-3.0, gratuito; distribuição deve respeitar a licença):
https://github.com/psycopg/psycopg/blob/master/LICENSE.txt.
O pacote fica em `platform/registry/registry_service`, sem criar `platform/__init__.py`.

Um arquivo local de segredos associa cada token administrativo aleatório a exatamente
um inquilino. O token determina o filtro de todas as operações administrativas; não se
aceita inquilino enviado no corpo como autorização. Os papéis finos e TOTP continuam no
item 1.6. Todos os administradores provisórios têm acesso de gestão ao próprio inquilino.

Dispositivos recebem um token aleatório de 256 bits, retornado uma única vez no cadastro.
O banco guarda SHA-256 para autenticação HTTP e PBKDF2-HMAC-SHA512 para Mosquitto 2.0
(100000 iterações, salt de 12 bytes e saída de 64 bytes). Não guarda o token original.
O formato foi conferido no código oficial do Mosquitto:
https://github.com/eclipse-mosquitto/mosquitto/blob/v2.0.22/apps/mosquitto_passwd/mosquitto_passwd.c.

O exportador administrativo gera senhas e ACLs versionadas e substitui o arquivo de
configuração ativo por rename atômico. Um broker separado em 1884 usa o cadastro; a demo
anterior em 1883 permanece disponível. A aplicação não recebe acesso ao Docker socket.

## Consequências
A revogação HTTP é imediata. Para MQTT, o administrador precisa exportar novamente e
reiniciar o broker cadastrado; isso também desconecta sessões antigas. A API devolve
`mqtt_aplicacao_pendente: true`, sem alegar revogação instantânea no broker. Esse procedimento
interrompe brevemente todos os dispositivos desse broker. A sincronização automática e
a disponibilidade contínua ficam para uma evolução de provisionamento.

Perfis e domínios iniciais vêm de JSON. As unidades são um subconjunto configurável de UCUM,
não um interpretador completo da gramática UCUM. Novo perfil usa outro ID; edição de
perfil e rotação de tokens não fazem parte desta entrega. O seed não sobrescreve cadastros.

O status usa o horário de recepção do heartbeat autenticado e a tolerância do perfil.
MQTT ainda não atualiza esse horário: a integração será feita pelo serviço de ingestão (1.2).
Não há vínculo automático entre o token HTTP e um token administrativo.
