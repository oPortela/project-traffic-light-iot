# Identidade e TLS

Esta configuração é para execução local. Prepare a central pelo guia de ingestão.
Execute `python scripts/init_security.py`, preservando os segredos fora do Git.
Adicione `-f deploy/docker-compose.security.yml` aos arquivos Compose da central e
suba `keycloak-db keycloak gateway registry data-api`. Defina `IOT_TENANTS` com a
lista de inquilinos autorizados, separados por vírgula.

O gateway usa porta 8443 e nomes auth.localhost, registry.localhost,
ingest.localhost e data.localhost. O certificado é assinado pela CA local em
`deploy/secrets/tls/ca.crt`. Configure essa CA no cliente, sem desativar a verificação.
Em ambientes que não resolvem subdomínios localhost, adicione resolução local.

Antes de criar usuários, execute `python scripts/configure_identity.py`. Esse passo
configura o atributo `inquilino` como administrável apenas no Keycloak. Acesse
`https://auth.localhost:8443/admin` com bootstrap-admin e a senha do arquivo
`deploy/secrets/keycloak-admin-password`. Crie usuários do realm iot, atribua o
inquilino e um dos papéis. Cada usuário deve configurar seu próprio TOTP no primeiro
login. A aplicação não gera nem guarda o segundo fator do usuário.

| Papel | Permissões nas APIs |
|---|---|
| administrador / gestor | Consultar, cadastrar, regras, reconhecer e revogar |
| integrador | Consultar, cadastrar e criar regras; sem revogar |
| operador | Consultar e reconhecer alarmes |
| leitor | Somente consultar |

Use authorization code + PKCE com o client iot-portal. O token deve ter audience
iot-api e claim inquilino autorizado. O realm exige TOTP para todos os usuários;
o fluxo direto de senha não é habilitado para esse client. Revise permissões de
administradores do próprio Keycloak separadamente dos papéis da aplicação.

Para observabilidade, acrescente `deploy/docker-compose.observability.yml` e
`--profile obs`. Prometheus: localhost:9090. Grafana: localhost:3000, usuário admin
e senha do arquivo grafana-password. O painel IoT é provisionado automaticamente.
Esses serviços não são publicados externamente pelo gateway.

Para exposição pública, configure domínio, certificados de CA pública, issuer,
redirect URIs e firewall. A implantação local não publica uma URL na internet.
