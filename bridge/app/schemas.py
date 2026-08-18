from typing import Any

from pydantic import BaseModel, Field


class PortalIdentityRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=80)
    customer_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=254)
    phone_number: str = Field(default="", max_length=32)


class WifiChangeRequest(BaseModel):
    tenant_id: str
    customer_id: str
    device_id: str
    network: str = Field(pattern="^(2.4ghz|5ghz)$")
    ssid: str | None = Field(default=None, min_length=1, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=63)


class ChatwootWebhook(BaseModel):
    event: str
    id: int | None = None
    content: str | None = None
    message_type: str | int | None = None
    private: bool = False
    conversation: dict[str, Any] = Field(default_factory=dict)
    sender: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] = Field(default_factory=dict)

