# Gêmeo desejado e relatado

Com Bearer autorizado, envie `PUT /api/v1/dispositivos/{id}/gemeo/desejado` com
`{"wait":15}`. `GET /api/v1/dispositivos/{id}/gemeo` mostra desejado, relatado,
revisão e se existe diferença pendente. O perfil enumera os campos configuráveis.

O executor envia somente diferenças como comando `config`, sem retenção MQTT,
e tenta novamente a cada 30 segundos até receber estado convergente. A revisão é
persistida; reenvios de uma mesma diferença conservam o identificador. Um novo
relato divergente permite corrigir alterações locais. Revogação impede novos envios.

O semáforo combina diferenças com a configuração atual. Continua recusando mudanças
enquanto está em execução; pare-o antes de alterar tempos ou ROI. A plataforma não
contorna essa regra de segurança. O comando permanece pendente até poder ser aplicado.

Para perfis criados antes desta etapa, crie uma nova versão com `campos.estado` e
`configuraveis` e provisione um dispositivo associado. O seed não sobrescreve perfis
customizados existentes. Os valores do perfil padrão respeitam os limites do semáforo.
