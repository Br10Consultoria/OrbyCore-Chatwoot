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

Em Ubuntu ou Debian, o instalador configura o repositório oficial e instala
Docker Engine, Buildx e o plugin Compose quando ainda não estiverem disponíveis.
Depois ele prepara banco, Redis, Chatwoot, bridge, worker e proxy HTTPS e aguarda
os serviços iniciarem corretamente.

## Configuração inicial no Chatwoot

O procedimento completo, incluindo associação automática do assinante, está em
[docs/PASSO-A-PASSO-INTEGRACAO.md](docs/PASSO-A-PASSO-INTEGRACAO.md).

1. Acesse `https://<CHATWOOT_DOMAIN>` e crie o administrador.
2. Execute `sudo ./scripts/configurar-integracao.sh`. O assistente cria ou
   reutiliza a caixa Website `Portal Sac`, ativa Identity Validation, descobre os
   IDs, gera os tokens, cria e vincula o usuário técnico e cadastra o webhook.
3. Para rotacionar uma chave HMAC exposta, execute uma vez
   `sudo ROTATE_CHATWOOT_HMAC=true ./scripts/configurar-integracao.sh`.
   Para rotacionar o token da URL do webhook, use
   `sudo ROTATE_CHATWOOT_WEBHOOK=true ./scripts/configurar-integracao.sh`.
4. O webhook criado automaticamente usa a URL:

```text
https://<CHATWOOT_DOMAIN>/orby-bridge/v1/chatwoot/webhooks/<CHATWOOT_WEBHOOK_TOKEN>
```

Os eventos `message_created`, `conversation_created` e
`conversation_status_changed` são assinados automaticamente. O evento de criação
abre o menu clicável; as escolhas direcionam a conversa para as equipes
**suporte técnico**, **financeiro** ou **comercial**, criadas pelo próprio script.

5. O próprio assistente reinicia o bridge e o worker após alterar o `.env`.

```bash
docker compose up -d --build bridge bridge-worker
```

## Menu e autosserviço

- `/menu`, `oi`, `olá`, `bom dia`, `boa tarde` ou `boa noite`: apresenta o menu clicável;
- `/boleto`, `boleto`, `pix` ou `segunda via`: consulta as faturas abertas no OrbyCore;
- `/status`: consulta no OrbyCore a situação resumida dos equipamentos do cliente;
- `/wifi`, `wifi` ou `senha wifi`: abre o submenu de nome, senha e estado das redes;
- o menu técnico consulta conexão e dispositivos conectados e direciona atualização,
  reinicialização e Wi-Fi para a tela autenticada do Portal SAC;
- assuntos financeiros, técnicos e comerciais são atribuídos à equipe correta.

Mensagens livres são classificadas somente por assunto e encaminhadas à fila humana;
o bot não inventa respostas nem executa ações destrutivas.

Nome, texto de boas-vindas e cor do widget podem ser definidos no `.env` por
`CHATWOOT_WIDGET_WELCOME_TITLE`, `CHATWOOT_WIDGET_WELCOME_TAGLINE` e
`CHATWOOT_WIDGET_COLOR`. Execute `./scripts/configurar-integracao.sh` novamente
para aplicar a personalização e reconciliar equipes, membros e roteamento.

### Limites das ações ACS para o assinante

O menu expõe somente consulta de estado, contagem de dispositivos, atualização
de dados, Wi-Fi e reinicialização. Senhas nunca passam pela conversa: o cliente é
levado ao formulário autenticado, que aplica confirmação, rate limit e auditoria.
Reset de fábrica, firmware, PPPoE, VLAN e parâmetros TR-069 arbitrários permanecem
restritos aos operadores do provedor.

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
- [x] menus clicáveis, personalização do widget e roteamento automático por equipe;
- [x] autosserviço ACS seguro para status, Wi-Fi, atualização, clientes e reinício;
- [x] componente do widget e deep link Wi-Fi no Portal SAC;
- [x] persistência e backup verificado de banco e anexos;
- [ ] teste ponta a ponta com Chatwoot e OrbySync reais;
- [ ] homologação periódica de restauração e carga no ambiente do provedor.
