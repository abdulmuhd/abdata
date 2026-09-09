"""Domain errors mapped to HTTP responses centrally in main.py."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class InsufficientFundsError(AppError):
    status_code = 400
    code = "insufficient_funds"


class PinLockedError(AppError):
    status_code = 423
    code = "pin_locked"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"
