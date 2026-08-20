# Integração Chatwoot com OrbyCore

## Como o cliente é associado automaticamente

Não existe cadastro manual de `tenant_id` ou `customer_id` no Chatwoot.

1. O assinante entra no Portal SAC do OrbyCore.
2. O token da sessão do portal já contém o tenant e o cliente autenticados.
3. O backend do OrbyCore envia ao bridge apenas os dados confirmados no banco:
   `tenant_id`, `customer_id`, nome, e-mail e telefone.
4. O bridge cria o identificador estável `orby:<tenant_id>:<customer_id>` e a
   assinatura HMAC exigida pelo Chatwoot.
5. O widget registra esse identificador no contato/conversa.
6. Nos webhooks seguintes o bridge lê o identificador, extrai os dois UUIDs e
   consulta o OrbyCore usando o ServiceToken e `X-Tenant-ID`.

O navegador nunca escolhe esses UUIDs e o Chatwoot não se torna a fonte de
verdade. O OrbyCore sempre revalida tenant, cliente, contrato e equipamento.

## 1. Preparar DNS e VM

Crie um registro `A`, por exemplo `chat.provedor.com.br`, apontando para o IP
público da VM. Libere TCP 80 e 443. Não execute outro proxy nessas portas.

## 2. Criar o token no OrbyCore

No OrbyCore, crie um ServiceToken exclusivo chamado `Chatwoot`, com a permissão
`customers.view`. Se usar ACL de IP, autorize o IP público da VM do Chatwoot.
Copie o valor exibido; ele não volta a ser mostrado.

## 3. Instalar o Chatwoot

```bash
git clone https://github.com/Br10Consultoria/OrbyCore-Chatwoot.git /opt/orbycore-chatwoot
cd /opt/orbycore-chatwoot
chmod +x scripts/*.sh
sudo ./scripts/instalar.sh
```

O assistente solicita domínio, e-mail remetente, URL do OrbyCore, URL do Portal
SAC e ServiceToken. Senhas do PostgreSQL/Redis e segredos internos são gerados
automaticamente. SMTP pode ser preenchido posteriormente no `.env`.

## 4. Criar a conta e a caixa no Chatwoot

1. Abra `https://chat.provedor.com.br` e crie o administrador.
2. A caixa **Website**, o usuário técnico, os tokens, o HMAC e o webhook podem
   ser criados automaticamente na etapa seguinte. Se já existir uma caixa
   chamada **Portal Sac**, ela será reutilizada.

## 5. Executar o assistente de vinculação

```bash
cd /opt/orbycore-chatwoot
sudo ./scripts/configurar-integracao.sh
```

O script localiza a única conta existente, cria ou atualiza a caixa `Portal Sac`,
ativa Identity Validation, configura o domínio do portal, cria um usuário
técnico, vincula o agente à caixa, cadastra o webhook, atualiza o `.env` e recria
bridge/Caddy. Se houver mais de uma conta, defina antes `CHATWOOT_ACCOUNT_ID` no
`.env`.

Para trocar uma chave HMAC que tenha sido exposta, execute uma vez:

```bash
sudo ROTATE_CHATWOOT_HMAC=true ./scripts/configurar-integracao.sh
```

Para trocar também o token secreto da URL do webhook:

```bash
sudo ROTATE_CHATWOOT_WEBHOOK=true ./scripts/configurar-integracao.sh
```

O assistente aguarda o bridge interno e o endpoint HTTPS ficarem prontos. A
recriação usa `--no-deps`, portanto não reinicia Rails, Sidekiq, PostgreSQL ou
Redis durante uma simples alteração da integração.

## 6. Conferir o webhook

O webhook e os eventos `message_created`, `conversation_created` e
`conversation_status_changed` são cadastrados automaticamente. A URL e o ID são
mostrados pelo assistente para conferência.

## 7. Habilitar o widget no Portal SAC do OrbyCore

Na VM do Chatwoot, consulte o token gerado durante a instalação:

```bash
cd /opt/orbycore-chatwoot
sudo grep '^BRIDGE_SERVICE_TOKEN=' .env
```

Na VM do OrbyCore, inclua no `.env`:

```env
CHATWOOT_BRIDGE_URL=https://chat.provedor.com.br/orby-bridge
CHATWOOT_BRIDGE_SERVICE_TOKEN=valor_do_BRIDGE_SERVICE_TOKEN
CHATWOOT_PUBLIC_ORIGIN=https://chat.provedor.com.br
CHATWOOT_PUBLIC_WS_ORIGIN=wss://chat.provedor.com.br
```

Recrie backend e frontend:

```bash
cd /opt/orbycore
sudo docker compose up -d --build --force-recreate backend frontend edge
```

O ServiceToken do OrbyCore e o Bridge Service Token são segredos diferentes e
protegem direções diferentes da comunicação.

## 8. Validar

```bash
curl -fsS https://chat.provedor.com.br/orby-bridge/ready
docker compose ps
docker compose logs --tail=100 bridge bridge-worker
sudo ./scripts/validar-integracao.sh
```

No Portal SAC, entre com um cliente real e abra o chat. No Chatwoot, o contato
deve ter identificador iniciado por `orby:`. Teste `/boleto`; a resposta deve
listar somente as faturas abertas daquele cliente. `/status` deve resumir apenas
os equipamentos vinculados. `/wifi` deve direcionar para
a tela segura do portal, sem pedir a senha na conversa.

## Valores globais e valores automáticos

| Valor | Origem |
|---|---|
| `ORBYCORE_API_URL` | informado na instalação |
| `ORBYCORE_SERVICE_TOKEN` | criado no OrbyCore e informado na instalação |
| `CHATWOOT_API_TOKEN` | criado no Chatwoot e informado na vinculação |
| `CHATWOOT_ACCOUNT_ID` | exibido pelo Chatwoot |
| `CHATWOOT_WEBHOOK_TOKEN` | gerado automaticamente pelo instalador |
| `tenant_id` | derivado da sessão autenticada do Portal SAC |
| `customer_id` | derivado da sessão autenticada do Portal SAC |

Nunca coloque ServiceToken, API Token ou HMAC Token no frontend, em URL pública,
em ticket ou em repositório Git.
