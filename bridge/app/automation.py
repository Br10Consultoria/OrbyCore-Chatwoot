import logging
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from .clients import ChatwootClient, OrbyCoreClient, UpstreamError
from .config import Settings

logger = logging.getLogger(__name__)

MAIN_MENU = [
    {"title": "Suporte técnico e conexão", "value": "menu_support"},
    {"title": "Configurar Wi-Fi", "value": "menu_wifi"},
    {"title": "Financeiro e segunda via", "value": "menu_financial"},
    {"title": "Planos e contratação", "value": "menu_commercial"},
    {"title": "Falar com atendente", "value": "human_support"},
]

SUPPORT_MENU = [
    {"title": "Ver status da conexão", "value": "device_status"},
    {"title": "Ver dispositivos conectados", "value": "connected_devices"},
    {"title": "Atualizar dados do equipamento", "value": "device_refresh"},
    {"title": "Reiniciar modem/ONT", "value": "device_reboot"},
    {"title": "Falar com suporte técnico", "value": "human_support"},
    {"title": "Voltar ao menu principal", "value": "menu_main"},
]

WIFI_MENU = [
    {"title": "Alterar nome da rede (SSID)", "value": "wifi_ssid"},
    {"title": "Alterar senha do Wi-Fi", "value": "wifi_password"},
    {"title": "Ativar ou desativar uma rede", "value": "wifi_enabled"},
    {"title": "Ver redes e dispositivos", "value": "connected_devices"},
    {"title": "Falar com suporte técnico", "value": "human_support"},
    {"title": "Voltar ao menu principal", "value": "menu_main"},
]

FINANCIAL_MENU = [
    {"title": "Consultar segunda via ou PIX", "value": "invoice_open"},
    {"title": "Falar com o financeiro", "value": "human_financial"},
    {"title": "Voltar ao menu principal", "value": "menu_main"},
]


def _normalized(content: str) -> str:
    value = " ".join(content.lower().strip().split())
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )


def normalize_command(content: str, prefix: str = "/") -> str:
    value = _normalized(content)
    aliases = {
        "menu": "menu",
        "menu_main": "menu",
        "ajuda": "menu",
        "oi": "menu",
        "ola": "menu",
        "bom dia": "menu",
        "boa tarde": "menu",
        "boa noite": "menu",
        f"{prefix}menu": "menu",
        "menu_support": "support",
        "suporte tecnico e conexao": "support",
        "suporte": "support",
        "suporte tecnico": "support",
        "problema de conexao": "support",
        "menu_financial": "financial",
        "financeiro e segunda via": "financial",
        "financeiro": "financial",
        "menu_commercial": "commercial",
        "comercial": "commercial",
        "planos e contratacao": "commercial",
        "segunda via": "invoice",
        "2 via": "invoice",
        "boleto": "invoice",
        "pix": "invoice",
        "invoice_open": "invoice",
        "consultar segunda via ou pix": "invoice",
        f"{prefix}boleto": "invoice",
        "status": "status",
        "equipamento": "status",
        "device_status": "status",
        "ver status da conexao": "status",
        f"{prefix}status": "status",
        "menu_wifi": "wifi",
        "configurar wi-fi": "wifi",
        "trocar wifi": "wifi",
        "senha wifi": "wifi_password",
        "wifi": "wifi",
        f"{prefix}wifi": "wifi",
        "wifi_ssid": "wifi_ssid",
        "alterar nome da rede (ssid)": "wifi_ssid",
        "wifi_password": "wifi_password",
        "alterar senha do wi-fi": "wifi_password",
        "wifi_enabled": "wifi_enabled",
        "ativar ou desativar uma rede": "wifi_enabled",
        "connected_devices": "clients",
        "ver dispositivos conectados": "clients",
        "ver redes e dispositivos": "clients",
        "device_refresh": "refresh",
        "atualizar dados do equipamento": "refresh",
        "device_reboot": "reboot",
        "reiniciar modem/ont": "reboot",
        "reiniciar modem": "reboot",
        "human_support": "human_support",
        "falar com suporte tecnico": "human_support",
        "falar com atendente": "human_support",
        "human_financial": "human_financial",
        "falar com o financeiro": "human_financial",
    }
    return aliases.get(value, "")


def infer_department(content: str) -> str:
    value = _normalized(content)
    if any(word in value for word in ("boleto", "pix", "fatura", "pagamento", "finance")):
        return "financial"
    if any(word in value for word in ("plano", "contrat", "adesao", "comercial", "venda")):
        return "commercial"
    return "support"


def customer_context(payload: dict[str, Any]) -> tuple[str, str] | None:
    sender = payload.get("sender") or {}
    identifier = str(sender.get("identifier") or "")
    if not identifier:
        identifier = str(
            ((payload.get("conversation") or {}).get("meta") or {})
            .get("sender", {})
            .get("identifier")
            or ""
        )
    parts = identifier.split(":", 2)
    if len(parts) != 3 or parts[0] != "orby" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def invoice_message(items: Any) -> str:
    invoices = items.get("invoices", items) if isinstance(items, dict) else items
    if not isinstance(invoices, list) or not invoices:
        return "Não encontrei faturas em aberto. Se precisar, o setor financeiro pode conferir sua conta."
    lines = ["Encontrei estas faturas em aberto:"]
    for item in invoices[:5]:
        if not isinstance(item, dict):
            continue
        try:
            amount = Decimal(str(item.get("balance_due") or item.get("total_amount") or "0"))
            amount_text = f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (InvalidOperation, ValueError):
            amount_text = "valor indisponível"
        lines.append(
            f"\nFatura {item.get('number', '—')} · vencimento {item.get('due_date', '—')} · {amount_text}"
        )
        if item.get("payment_url"):
            lines.append(f"Boleto: {item['payment_url']}")
        if item.get("pix_emv"):
            lines.append(f"PIX copia e cola: {item['pix_emv']}")
    lines.append("\nOs dados vieram diretamente do OrbyCore.")
    return "\n".join(lines)


def equipment_message(items: Any, *, clients_only: bool = False) -> str:
    equipment = items.get("equipment", items) if isinstance(items, dict) else items
    if not isinstance(equipment, list) or not equipment:
        return "Não encontrei equipamento gerenciado vinculado ao seu contrato."
    lines = [
        "Dispositivos conectados às suas redes:"
        if clients_only
        else "Situação dos seus equipamentos:"
    ]
    for item in equipment[:5]:
        if not isinstance(item, dict):
            continue
        label = (
            " ".join(
                part
                for part in (str(item.get("manufacturer") or ""), str(item.get("model") or ""))
                if part
            )
            or "CPE"
        )
        client_count = int(item.get("wifi_clients_count") or 0)
        lines.append(
            f"• {label} · serial {item.get('serial_number') or 'não informado'} · "
            f"status {item.get('status') or 'desconhecido'} · {client_count} conectado(s) no Wi-Fi"
        )
        networks = item.get("wifi_networks") or []
        for network in networks[:4] if isinstance(networks, list) else []:
            if isinstance(network, dict) and network.get("ssid"):
                lines.append(
                    f"  - {network.get('network') or 'Wi-Fi'}: {network['ssid']} · "
                    f"{int(network.get('clients') or 0)} dispositivo(s)"
                )
        if not clients_only and item.get("last_inform_at"):
            lines.append(f"  Última comunicação: {item['last_inform_at']}")
    lines.append("Dados atualizados pelo OrbySync/ACS.")
    return "\n".join(lines)


def _conversation_id(payload: dict[str, Any]) -> int:
    conversation = payload.get("conversation") or {}
    return int(conversation.get("id") or payload.get("conversation_id") or payload.get("id") or 0)


async def _send_menu(
    chatwoot: ChatwootClient,
    conversation_id: int,
    content: str,
    items: list[dict[str, str]],
) -> None:
    message = await chatwoot.send_message(
        conversation_id,
        content,
        content_type="input_select",
        content_attributes={"items": items},
    )
    if isinstance(message, dict):
        returned_type = message.get("content_type")
        returned_items = (message.get("content_attributes") or {}).get("items")
        if returned_type not in ("input_select", 4) or not returned_items:
            raise UpstreamError(
                "Chatwoot não preservou content_type=input_select ou os itens do menu"
            )
    logger.info(
        "Menu interativo enviado",
        extra={"conversation_id": conversation_id, "items": len(items)},
    )


async def _assign(
    chatwoot: ChatwootClient, conversation_id: int, settings: Settings, department: str
) -> None:
    team_id = {
        "support": settings.chatwoot_team_support_id,
        "financial": settings.chatwoot_team_financial_id,
        "commercial": settings.chatwoot_team_commercial_id,
    }.get(department, 0)
    await chatwoot.assign_team(conversation_id, team_id)


async def process_automation(payload: dict[str, Any], settings: Settings) -> str:
    if not settings.automation_enabled:
        return "ignored"
    event = payload.get("event")
    conversation_id = _conversation_id(payload)
    if event == "conversation_created":
        if not conversation_id:
            return "invalid"
        await _send_menu(
            ChatwootClient(settings),
            conversation_id,
            "Olá! Escolha uma opção para eu direcionar seu atendimento:",
            MAIN_MENU,
        )
        return "menu"
    if event != "message_created" or payload.get("private"):
        return "ignored"
    message_type = payload.get("message_type")
    if message_type not in (0, "incoming"):
        return "ignored"
    if not conversation_id:
        return "invalid"

    content = str(payload.get("content") or "")
    command = normalize_command(content, settings.automation_trigger_prefix)
    chatwoot = ChatwootClient(settings)
    if command == "menu":
        await _send_menu(chatwoot, conversation_id, "Como posso ajudar?", MAIN_MENU)
        return "menu"
    if command == "support":
        await _assign(chatwoot, conversation_id, settings, "support")
        await _send_menu(
            chatwoot, conversation_id, "Escolha o atendimento técnico desejado:", SUPPORT_MENU
        )
        return "support"
    if command == "financial":
        await _assign(chatwoot, conversation_id, settings, "financial")
        await _send_menu(chatwoot, conversation_id, "Escolha uma opção financeira:", FINANCIAL_MENU)
        return "financial"
    if command == "commercial":
        await _assign(chatwoot, conversation_id, settings, "commercial")
        await chatwoot.send_message(
            conversation_id,
            "Encaminhei sua conversa ao setor Comercial. Informe o plano ou serviço que deseja contratar.",
        )
        return "commercial"
    if command in {"human_support", "human_financial"}:
        department = "financial" if command == "human_financial" else "support"
        await _assign(chatwoot, conversation_id, settings, department)
        await chatwoot.send_message(
            conversation_id,
            "Pronto! Sua conversa foi direcionada ao setor correto. Um atendente continuará por aqui.",
        )
        return command

    context = customer_context(payload)
    if context is None:
        await _assign(chatwoot, conversation_id, settings, infer_department(content))
        await chatwoot.send_message(
            conversation_id,
            "Para proteger seus dados, use o chat dentro da Central do Assinante ou aguarde um atendente.",
        )
        return "unidentified"
    tenant_id, customer_id = context

    if command == "wifi":
        await _assign(chatwoot, conversation_id, settings, "support")
        await _send_menu(chatwoot, conversation_id, "O que deseja configurar no Wi-Fi?", WIFI_MENU)
        return "wifi"
    if command in {"wifi_ssid", "wifi_password", "wifi_enabled"}:
        await _assign(chatwoot, conversation_id, settings, "support")
        link = f"{settings.orbycore_portal_url.rstrip('/')}?section=equipment&action=wifi"
        await chatwoot.send_message(
            conversation_id,
            "Por segurança, nome e senha não são digitados na conversa. Abra a tela autenticada "
            f"para escolher a rede 2,4/5 GHz e aplicar a alteração: {link}",
        )
        return command
    if command in {"refresh", "reboot"}:
        await _assign(chatwoot, conversation_id, settings, "support")
        link = f"{settings.orbycore_portal_url.rstrip('/')}?section=equipment&action={command}"
        action = "Atualizar conexão" if command == "refresh" else "Reiniciar equipamento"
        await chatwoot.send_message(
            conversation_id,
            f"Abra seus equipamentos no Portal SAC e confirme “{action}”. A ação será auditada: {link}",
        )
        return command

    try:
        orbycore = OrbyCoreClient(settings)
        if command in {"status", "clients"}:
            await _assign(chatwoot, conversation_id, settings, "support")
            data = await orbycore.devices(tenant_id, customer_id)
            message = equipment_message(data, clients_only=command == "clients")
        elif command == "invoice":
            await _assign(chatwoot, conversation_id, settings, "financial")
            data = await orbycore.open_invoices(tenant_id, customer_id)
            message = invoice_message(data)
        else:
            department = infer_department(content)
            await _assign(chatwoot, conversation_id, settings, department)
            await chatwoot.send_message(
                conversation_id,
                "Recebi sua mensagem e encaminhei ao setor responsável. Um atendente continuará por aqui.",
            )
            return f"human_{department}"
        await chatwoot.send_message(conversation_id, message)
        return command
    except UpstreamError:
        logger.exception("Falha ao consultar o OrbyCore", extra={"tenant_id": tenant_id})
        await _assign(chatwoot, conversation_id, settings, "support")
        await chatwoot.send_message(
            conversation_id,
            "Não consegui consultar seus dados agora. Um atendente continuará o atendimento.",
        )
        return "upstream_error"
