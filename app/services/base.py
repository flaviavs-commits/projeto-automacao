class ExternalServiceResult(dict):
    """Simple explicit response shape for service stubs."""


class BaseExternalService:
    """Base helper for integrations that should not call external APIs without credentials."""

    service_name = "external_service"

    def not_configured(self, action: str) -> ExternalServiceResult:
        return ExternalServiceResult(
            status="not_configured",
            service=self.service_name,
            action=action,
        )
