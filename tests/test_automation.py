from unittest.mock import AsyncMock, patch

import pytest

from app.automation import (
    MAIN_MENU,
    customer_context,
    equipment_message,
    invoice_message,
    normalize_command,
    process_automation,
)
from app.clients import ChatwootClient
from app.config import get_settings
from app.security import identifier_hash, safe_equal


def test_only_expected_commands_are_automated():
    assert normalize_command("/boleto") == "invoice"
    assert normalize_command("segunda via") == "invoice"
    assert normalize_command("/wifi") == "wifi"
    assert normalize_command("/status") == "status"
    assert normalize_command("boa tarde") == "menu"
    assert normalize_command("menu_support") == "support"
    assert normalize_command("wifi_password") == "wifi_password"
    assert normalize_command("device_reboot") == "reboot"
    assert normalize_command("preciso cancelar meu contrato") == ""


def test_customer_context_requires_orby_identifier():
    payload = {"sender": {"identifier": "orby:tenant-1:customer-2"}}
    assert customer_context(payload) == ("tenant-1", "customer-2")
    assert customer_context({"sender": {"identifier": "customer-2"}}) is None


def test_invoice_response_contains_real_payment_data():
    message = invoice_message(
        {
            "invoices": [
                {
                    "number": "FAT-10",
                    "due_date": "2026-08-20",
                    "balance_due": "99.90",
                    "payment_url": "https://pay.example/invoice",
                    "pix_emv": "000201TEST",
                }
            ]
        }
    )
    assert "FAT-10" in message
    assert "R$ 99,90" in message
    assert "https://pay.example/invoice" in message
    assert "000201TEST" in message


def test_equipment_response_contains_only_operational_summary():
    message = equipment_message(
        {
            "equipment": [
                {
                    "manufacturer": "Huawei",
                    "model": "EG8145X6",
                    "serial_number": "ABC1",
                    "status": "online",
                }
            ]
        }
    )
    assert "Huawei EG8145X6" in message
    assert "ABC1" in message
    assert "online" in message


@pytest.mark.asyncio
async def test_conversation_created_sends_clickable_main_menu():
    with patch.object(ChatwootClient, "send_message", new=AsyncMock()) as send:
        result = await process_automation(
            {"event": "conversation_created", "id": 77}, get_settings()
        )

    assert result == "menu"
    assert send.await_args.kwargs["content_type"] == "input_select"
    assert send.await_args.kwargs["content_attributes"]["items"] == MAIN_MENU


@pytest.mark.asyncio
async def test_financial_selection_assigns_team_and_opens_submenu():
    settings = get_settings().model_copy(update={"chatwoot_team_financial_id": 23})
    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "menu_financial",
        "conversation": {"id": 81},
    }
    with (
        patch.object(ChatwootClient, "assign_team", new=AsyncMock()) as assign,
        patch.object(ChatwootClient, "send_message", new=AsyncMock()) as send,
    ):
        result = await process_automation(payload, settings)

    assert result == "financial"
    assign.assert_awaited_once_with(81, 23)
    assert send.await_args.kwargs["content_type"] == "input_select"


def test_hmac_identity_is_stable_and_secrets_compare_safely():
    digest = identifier_hash("orby:t:c", "secret")
    assert len(digest) == 64
    assert digest == identifier_hash("orby:t:c", "secret")
    assert safe_equal("same", "same") is True
    assert safe_equal("same", "other") is False
