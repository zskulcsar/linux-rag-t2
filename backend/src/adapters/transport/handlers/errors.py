"""Transport-layer error types shared across handler modules."""

from typing import Any


class TransportError(RuntimeError):
    """Base transport-level error mapped to standardized response payloads."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        remediation: str | None = None,
    ) -> None:
        """Initialize the transport error."""

        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.remediation = remediation

    def to_payload(self) -> dict[str, Any]:
        """Convert the error into a JSON-serializable payload."""

        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload


class IndexUnavailableError(TransportError):
    """Raised when the content index is stale or missing."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(
            status=409,
            code=code,
            message=message,
            remediation=remediation,
        )


__all__ = ["TransportError", "IndexUnavailableError"]
