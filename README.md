# OrbyCore Chatwoot

Base self-hosted para atendimento humano do OrbyCore usando Chatwoot Community Edition, com automação limitada e segura para:

1. segunda via de boleto/PIX;
2. situação dos equipamentos vinculados;
3. alteração de nome ou senha do Wi-Fi pela tela segura do Portal SAC.

Qualquer outro assunto segue para um atendente humano. O bridge não tenta responder contratos, cancelamentos, suporte técnico ou outros temas automaticamente.

## Arquitetura

```text
Portal SAC OrbyCore ── identidade HMAC ──> Widget Chatwoot
        │                                      │
        │                                      ├── atendimento humano
        │                                      └── /boleto e /wifi
        │                                                   │
        └──────────── API interna autenticada <── bridge ───┘
```

O OrbyCore permanece como fonte oficial de tenants, clientes, contratos, faturas, CPEs, comandos ACS e auditoria. O Chatwoot armazena conversas e a operação dos atendentes.

## Serviços

- Chatwoot Rails Community Edition;
- Sidekiq;
- PostgreSQL 16 com pgvector;
- Redis;
- bridge FastAPI;
- Caddy com HTTPS automático.

Nenhum banco, Redis ou bridge é publicado diretamente na internet.

## Segurança adotada

- identidade do cliente assinada com HMAC do Inbox;
- identificador estável `orby:<tenant_id>:<customer_id>`;
- endpoint de identidade acessível somente com token de serviço;
- webhook em caminho com token aleatório, validação de conta/inbox e idempotência por evento;
- fila Redis persistente, retentativas, recuperação após reinício e dead-letter;
- isolamento de tenant exigido no contrato da API OrbyCore;
- senha Wi-Fi nunca é digitada nem armazenada na conversa;
- autosserviço só reage aos comandos previstos;
- cadastros públicos do Chatwoot desativados por padrão.

## Preparação

```bash
git clone https://github.com/Br10Consultoria/OrbyCore-Chatwoot.git
cd OrbyCore-Chatwoot
cp .env.example .env
```

Gere os segredos:

```bash
openssl rand -hex 64
openssl rand -base64 48
openssl rand -base64 48
openssl rand -base64 32
openssl rand -base64 32
```

Preencha domínio, SMTP e segredos no `.env`. Na primeira instalação:

```bash
chmod +x scripts/*.sh
./scripts/instalar.sh
```

## Configuração inicial no Chatwoot

O procedimento completo, incluindo associação automática do assinante, está em
[docs/PASSO-A-PASSO-INTEGRACAO.md](docs/PASSO-A-PASSO-INTEGRACAO.md).

1. Acesse `https://<CHATWOOT_DOMAIN>` e crie o administrador.
2. Crie uma caixa **Website** chamada `Portal SAC`.
3. Ative **Identity Validation** e copie o HMAC Token para `CHATWOOT_INBOX_HMAC_TOKEN`.
4. Copie o Website Token para `CHATWOOT_INBOX_IDENTIFIER`.
5. Crie um usuário exclusivo de integração e copie seu API Access Token para `CHATWOOT_API_TOKEN`.
6. Confirme Account ID e Inbox ID no `.env`.
7. Cadastre o webhook:

```text
https://<CHATWOOT_DOMAIN>/orby-bridge/v1/chatwoot/webhooks/<CHATWOOT_WEBHOOK_TOKEN>
```

Assine pelo menos `message_created`, `conversation_created` e `conversation_status_changed`.

8. Reinicie o bridge e o worker após alterar o `.env`:

```bash
docker compose up -d --build bridge bridge-worker
```

## Comandos do autosserviço

- `/menu`: apresenta as opções disponíveis;
- `/boleto`, `boleto`, `pix` ou `segunda via`: consulta as faturas abertas no OrbyCore;
- `/status`: consulta no OrbyCore a situação resumida dos equipamentos do cliente;
- `/wifi`, `wifi` ou `senha wifi`: envia o cliente para a tela segura do Portal SAC.

Mensagens diferentes não recebem resposta automática e permanecem na fila humana.

## API do bridge

### Identidade para o Portal

`POST /orby-bridge/v1/portal/identity`

Header: `Authorization: Bearer <BRIDGE_SERVICE_TOKEN>`

Esta rota deve ser chamada pelo backend OrbyCore, nunca diretamente pelo navegador.

### Alteração Wi-Fi segura (uso servidor a servidor)

`POST /orby-bridge/v1/portal/wifi`

Recebe a solicitação enviada pelo formulário autenticado e a encaminha ao OrbyCore. O OrbyCore valida cliente, contrato, CPE e rate limit antes de enfileirar o comando no OrbySync.

O contrato completo está em [docs/CONTRATO-ORBYCORE.md](docs/CONTRATO-ORBYCORE.md).

## Testes

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check bridge tests
pytest -q
```

## Atualização e backup

```bash
./scripts/atualizar.sh
```

`atualizar.sh` exige uma instalação existente, cria e verifica backup do PostgreSQL e dos anexos antes do `git pull`, migra anexos de containers antigos para o volume persistente, aplica as migrações e recria os serviços sem executar novamente o instalador. Para restaurar: `./scripts/restaurar.sh backups/AAAAMMDD-HHMMSS`.

## Estado do MVP

- [x] composição self-hosted isolada;
- [x] bridge e autenticação de serviço;
- [x] identidade HMAC para o widget;
- [x] webhook assíncrono, idempotente, com retry e dead-letter;
- [x] atendimento humano pelo Chatwoot;
- [x] segunda via via API OrbyCore;
- [x] fluxo Wi-Fi redirecionado para tela segura;
- [x] testes automatizados e CI com build do container;
- [x] endpoints internos correspondentes no OrbyCore;
- [x] componente do widget e deep link Wi-Fi no Portal SAC;
- [x] persistência e backup verificado de banco e anexos;
- [ ] teste ponta a ponta com Chatwoot e OrbySync reais;
- [ ] homologação periódica de restauração e carga no ambiente do provedor.
