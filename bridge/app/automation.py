import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from .clients import ChatwootClient, OrbyCoreClient, UpstreamError
from .config import Settings

logger = logging.getLogger(__name__)

MENU = (
    "Olá! Posso ajudar automaticamente apenas com:\n"
    "• /boleto — segunda via de boleto ou PIX\n"
    "• /wifi — alterar nome ou senha do Wi-Fi com segurança\n"
    "Para qualquer outro assunto, escreva sua mensagem e um atendente continuará o atendimento."
)


def normalize_command(content: str, prefix: str = "/") -> str:
    value = " ".join(content.lower().strip().split())
    aliases = {
        "menu": "menu",
        "ajuda": "menu",
        f"{prefix}menu": "menu",
        "segunda via": "invoice",
        "2 via": "invoice",
        "boleto": "invoice",
        "pix": "invoice",
        f"{prefix}boleto": "invoice",
        "trocar wifi": "wifi",
        "senha wifi": "wifi",
        "wifi": "wifi",
        f"{prefix}wifi": "wifi",
    }
    return aliases.get(value, "")


def customer_context(payload: dict[str, Any]) -> tuple[str, str] | None:
    sender = payload.get("sender") or {}
    identifier = str(sender.get("identifier") or "")
    if not identifier:
        identifier = str(
            ((payload.get("conversation") or {}).get("meta") or {}).get("sender", {}).get("identifier")
            or ""
        )
    parts = identifier.split(":", 2)
    if len(parts) != 3 or parts[0] != "orby" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def invoice_message(items: Any) -> str:
    invoices = items.get("invoices", items) if isinstance(items, dict) else items
    if not isinstance(invoices, list) or not invoices:
        return "Não encontrei faturas em aberto. Se precisar, um atendente pode conferir sua conta."
    lines = ["Encontrei estas faturas em aberto:"]
    for item in invoices[:5]:
        if not isinstance(item, dict):
            continue
        try:
            amount = Decimal(str(item.get("balance_due") or item.get("total_amount") or "0"))
            amount_text = f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (InvalidOperation, ValueError):
            amount_text = "valor indisponível"
        lines.append(f"\nFatura {item.get('number', '—')} · vencimento {item.get('due_date', '—')} · {amount_text}")
        if item.get("payment_url"):
            lines.append(f"Boleto: {item['payment_url']}")
        if item.get("pix_emv"):
            lines.append(f"PIX copia e cola: {item['pix_emv']}")
    lines.append("\nOs dados vieram diretamente do OrbyCore.")
    return "\n".join(lines)


async def process_automation(payload: dict[str, Any], settings: Settings) -> str:
    if not settings.automation_enabled or payload.get("event") != "message_created":
        return "ignored"
    if payload.get("private"):
        return "ignored"
    message_type = payload.get("message_type")
    if message_type not in (0, "incoming"):
        return "ignored"
    command = normalize_command(str(payload.get("content") or ""), settings.automation_trigger_prefix)
    if not command:
        return "human"
    conversation = payload.get("conversation") or {}
    conversation_id = int(conversation.get("id") or payload.get("conversation_id") or 0)
    if not conversation_id:
        return "invalid"
    chatwoot = ChatwootClient(settings)
    if command == "menu":
        await chatwoot.send_message(conversation_id, MENU)
        return "menu"
    context = customer_context(payload)
    if context is None:
        await chatwoot.send_message(
            conversation_id,
            "Para proteger seus dados, use o chat dentro da Central do Assinante ou aguarde um atendente.",
        )
        return "unidentified"
    tenant_id, customer_id = context
    if command == "wifi":
        link = f"{settings.orbycore_portal_url.rstrip('/')}?section=equipment&action=wifi"
        await chatwoot.send_message(
            conversation_id,
            "A senha não deve ser digitada na conversa. Abra a tela segura da Central do Assinante "
            f"para alterar o nome ou a senha do Wi-Fi: {link}",
        )
        return "wifi"
    try:
        data = await OrbyCoreClient(settings).open_invoices(tenant_id, customer_id)
        await chatwoot.send_message(conversation_id, invoice_message(data))
        return "invoice"
    except UpstreamError:
        logger.exception("Falha ao consultar segunda via", extra={"tenant_id": tenant_id})
        await chatwoot.send_message(
            conversation_id,
            "Não consegui consultar a segunda via agora. Um atendente continuará o atendimento.",
        )
        return "upstream_error"

