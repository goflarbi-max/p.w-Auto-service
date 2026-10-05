"""Provider-neutral SMS reminder service with a no-network mock provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SMSResult:
    """Outcome returned by an SMS provider."""

    success: bool
    provider_message_id: str | None = None
    error: str | None = None


class SMSProvider(ABC):
    """Contract implemented by current and future SMS providers."""

    @abstractmethod
    def send(self, phone_number: str, message: str) -> SMSResult:
        """Send one SMS message."""


class ConsoleSMSProvider(SMSProvider):
    """Development provider that prints instead of calling an external API."""

    def send(self, phone_number: str, message: str) -> SMSResult:
        """Print the SMS payload and report a successful mock delivery."""
        print(f"[MOCK SMS] To: {phone_number} | Message: {message}")
        return SMSResult(success=True, provider_message_id="console-mock")


def send_sms_reminder(
    phone_number: str,
    message: str,
    provider: SMSProvider | None = None,
) -> SMSResult:
    """Send an already-rendered reminder using the selected provider."""
    selected_provider = provider or ConsoleSMSProvider()
    return selected_provider.send(phone_number, message)
