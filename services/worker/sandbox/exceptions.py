"""Sandbox error type (M5.2): coded failures, safe messages only."""


class SandboxError(Exception):
    """Execution failure with a safe code (never credentials or secrets)."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
