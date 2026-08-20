from app.automation import customer_context, equipment_message, invoice_message, normalize_command
from app.security import identifier_hash, safe_equal


def test_only_expected_commands_are_automated():
    assert normalize_command("/boleto") == "invoice"
    assert normalize_command("segunda via") == "invoice"
    assert normalize_command("/wifi") == "wifi"
    assert normalize_command("/status") == "status"
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


def test_hmac_identity_is_stable_and_secrets_compare_safely():
    digest = identifier_hash("orby:t:c", "secret")
    assert len(digest) == 64
    assert digest == identifier_hash("orby:t:c", "secret")
    assert safe_equal("same", "same") is True
    assert safe_equal("same", "other") is False
