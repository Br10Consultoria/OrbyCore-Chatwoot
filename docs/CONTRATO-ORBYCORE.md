# Contrato da integração OrbyCore

O bridge nunca acessa diretamente o banco do OrbyCore. O OrbyCore continua sendo a fonte de verdade de tenant, cliente, contrato, fatura, equipamento, comando ACS e auditoria.

## Autenticação

Todas as rotas abaixo devem exigir:

- `Authorization: Bearer <ORBYCORE_SERVICE_TOKEN>`;
- `X-Tenant-ID: <uuid-do-tenant>`;
- validação de que o cliente e todos os objetos consultados pertencem ao tenant;
- rate limit, idempotência e auditoria `source=chatwoot`.

## Rotas necessárias no OrbyCore

### Segunda via

`GET /api/v1/integrations/chatwoot/customers/{customer_id}/invoices/open/`

Resposta:

```json
{
  "invoices": [
    {
      "id": "uuid",
      "number": "FAT-0001",
      "due_date": "2026-08-20",
      "balance_due": "99.90",
      "payment_url": "https://...",
      "pix_emv": "000201..."
    }
  ]
}
```

Nunca retornar documentos internos, tokens bancários ou credenciais do gateway.

### Equipamentos do cliente

`GET /api/v1/integrations/chatwoot/customers/{customer_id}/equipment/`

Retorna somente CPEs pertencentes a contratos do cliente e as redes que podem ser alteradas.

### Alteração Wi-Fi

`PATCH /api/v1/integrations/chatwoot/customers/{customer_id}/equipment/{device_id}/wifi/`

```json
{
  "tenant_id": "uuid",
  "customer_id": "uuid",
  "device_id": "uuid",
  "network": "2.4ghz",
  "ssid": "NovoNome",
  "password": "nova-senha-segura"
}
```

A senha deve chegar por formulário seguro do Portal SAC, nunca como mensagem Chatwoot. O OrbyCore deve reutilizar `enqueue_acs_command`, o limite de uma alteração por minuto e a auditoria já existentes no Portal.

## Identidade do widget

O Portal SAC autenticado chama um endpoint do próprio OrbyCore. O OrbyCore deriva tenant, cliente, nome e contatos da sessão e chama `POST /v1/portal/identity` no bridge. Nenhum identificador vindo do navegador deve ser aceito como autoridade.

