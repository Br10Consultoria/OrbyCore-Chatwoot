# Proxies móveis do Portal SAC

**Autor:** Manus AI  
**Status:** Implementado no bridge; requer configuração de segredo e reinício controlado da implantação.

## Visão geral

Os proxies móveis permitem que o SAC Mobile consulte faturas abertas, equipamentos do assinante e solicite alteração de Wi-Fi sem receber o `ORBYCORE_SERVICE_TOKEN`. O bridge mantém a credencial de serviço, deriva `tenant_id` e `customer_id` de uma sessão móvel HMAC de curta duração e encaminha a chamada às rotas de integração do OrbyCore. O repositório principal do OrbyCore não foi alterado.

| Caminho público | Método | Autorização | Finalidade |
|---|---|---|---|
| `/orby-bridge/v1/portal/mobile/sessions` | `POST` | `Bearer BRIDGE_SERVICE_TOKEN` | Uso exclusivo do Portal SAC autenticado; emite a sessão móvel e a identidade Chatwoot. |
| `/orby-bridge/v1/mobile/autoservice/invoices/open` | `GET` | Sessão móvel `Bearer` | Lista faturas abertas do próprio assinante. |
| `/orby-bridge/v1/mobile/autoservice/equipment` | `GET` | Sessão móvel `Bearer` | Lista apenas os CPEs pertencentes ao assinante. |
| `/orby-bridge/v1/mobile/autoservice/equipment/wifi` | `PATCH` | Sessão móvel `Bearer` | Solicita alteração de Wi-Fi de um equipamento do assinante. |

> O Caddy remove o prefixo `/orby-bridge/` antes de encaminhar ao FastAPI. Por isso, a aplicação interna registra as mesmas rotas sob `/v1/...`.

## Emissão e validação de sessão

Após o Portal SAC autenticar o assinante, seu backend chama a rota interna de emissão com `BRIDGE_SERVICE_TOKEN` e os dados derivados **da própria sessão do Portal**. O bridge devolve um JWT HMAC-SHA256 com `tid`, `cid`, `iss`, `aud=sac-mobile`, `iat`, `exp` e `jti`, além da identidade Chatwoot. O backend do Portal devolve apenas esse resultado ao aplicativo por meio do ticket de uso único já definido na Etapa 1 do SAC Mobile.

Os proxies nunca aceitam `tenant_id` ou `customer_id` enviados pelo aplicativo. Mesmo que esses campos sejam enviados no corpo da alteração Wi-Fi, eles são ignorados e substituídos pelos valores verificados no token. A senha de Wi-Fi não é escrita no log do bridge.

| Variável | Regra | Valor recomendado |
|---|---|---|
| `MOBILE_SESSION_HMAC_SECRET` | Obrigatória, segredo aleatório exclusivo do ambiente, mínimo de 32 caracteres. | Gerar 48+ bytes aleatórios e guardar no cofre de segredos. |
| `MOBILE_SESSION_ISSUER` | Identifica o emissor esperado no token. | `orbycore-chatwoot-bridge` |
| `MOBILE_SESSION_TTL_SECONDS` | Limite da sessão para autosserviço. | `900` (15 minutos) |

## Configuração do SAC Mobile

Para usar diretamente o bridge sem alterar o domínio do Portal SAC, configure no build do aplicativo:

```text
EXPO_PUBLIC_AUTOSERVICE_BRIDGE_ORIGIN=https://chat.seu-provedor.com.br/orby-bridge
```

Com essa variável, o aplicativo muda automaticamente as três rotas de autosserviço para `v1/mobile/autoservice/...`, preservando o `EXPO_PUBLIC_PORTAL_SAC_ORIGIN` original para login e troca de ticket. Não inclua nenhum token nesta configuração pública.

## Ativação

O administrador deve criar o segredo de sessão no cofre de variáveis da implantação, atualizar `MOBILE_SESSION_HMAC_SECRET` no serviço `bridge` e reiniciar o stack de forma controlada. Em seguida, o backend autenticado do Portal SAC deve chamar `POST /orby-bridge/v1/portal/mobile/sessions` com o `BRIDGE_SERVICE_TOKEN`, nunca o aplicativo. O `POST /v1/portal/identity` existente continua disponível para o widget web.

Antes de produção, confirme que as rotas upstream do OrbyCore para faturas, equipamentos e Wi-Fi estão disponíveis na instalação. O bridge não acessa o banco, não seleciona dispositivos por parâmetros do usuário e propaga a identidade derivada pelo Portal com `X-Tenant-ID` ao serviço de origem.

## Referências

[1]: https://www.rfc-editor.org/rfc/rfc7519 "RFC 7519 — JSON Web Token"
[2]: https://docs.python.org/3/library/hmac.html "Python hmac — comparação segura de mensagens"
[3]: https://github.com/Br10Consultoria/OrbyCore-Chatwoot/blob/main/docs/CONTRATO-ORBYCORE.md "Contrato de integração OrbyCore"
