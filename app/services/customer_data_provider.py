from __future__ import annotations

from typing import Protocol

from app.services.base import ExternalServiceResult


class CustomerDataProvider(Protocol):
    """Open interface for customer-status providers."""

    def lookup_customer_by_whatsapp(self, *, phone_number: str) -> ExternalServiceResult:
        ...
