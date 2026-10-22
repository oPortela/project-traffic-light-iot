# ADR-009 — Identidade e observabilidade

OIDC verifica assinatura RS256, issuer, audience, expiração e inquilino assinado.
O modo bootstrap continua disponível sem OIDC_ISSUER, apenas para laboratório local.
Com OIDC configurado, tokens bootstrap não são aceitos como alternativa.

O realm Keycloak exige senha e TOTP para todos os usuários da plataforma, incluindo
administradores. O client público usa authorization code com PKCE S256; password
grant fica desativado. O atributo inquilino só é editável por administradores do
Keycloak, configurado por `scripts/configure_identity.py` antes de criar usuários.

Traefik termina TLS. A CA gerada é local; publicação externa requer certificado
confiável e ajuste de hosts, issuer e redirect URIs. Não se instala confiança no
sistema operacional automaticamente. Métricas ficam fora dos roteadores públicos.

Licenças verificadas: [PyJWT MIT](https://github.com/jpadilla/pyjwt/blob/master/LICENSE),
[Prometheus Python Apache-2.0](https://github.com/prometheus/client_python/blob/master/LICENSE).
Keycloak, Traefik, Prometheus e Grafana seguem as licenças registradas no roadmap.
Referências de implementação: [Keycloak containers](https://www.keycloak.org/server/containers)
e [fluxos de autenticação/TOTP](https://www.keycloak.org/docs/latest/server_admin/index.html).

Logs de ingestão/persistência contêm correlation_id igual ao id_mensagem, sem
payload ou credenciais. Métricas HTTP usam a rota parametrizada, evitando alta
cardinalidade por dispositivo. Painéis administrativos de infraestrutura são locais.
