from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class NotFound(AppError):
    def __init__(self, what: str = "resource") -> None:
        # Deliberately 404 for foreign objects too, to avoid object enumeration.
        super().__init__("NOT_FOUND", f"{what} was not found.", 404)


class Forbidden(AppError):
    def __init__(self, message: str = "You may not perform this action.") -> None:
        super().__init__("FORBIDDEN", message, 403)


class Unauthorized(AppError):
    def __init__(self, message: str = "Sign in to continue.") -> None:
        super().__init__("UNAUTHORIZED", message, 401)


class Conflict(AppError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(code, message, 409, details or {})


class Validation(AppError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, 422, details or {})


class RateLimited(AppError):
    def __init__(self, message: str = "Too many requests. Please wait and retry.") -> None:
        super().__init__("RATE_LIMITED", message, 429)


class ProviderUnavailable(AppError):
    def __init__(self, message: str = "Payment provider is unavailable.", details: dict | None = None) -> None:
        super().__init__("PAYMENT_PROVIDER_UNAVAILABLE", message, 503, details or {})
