"""Investigation worker package (M6): orchestration plus browser reproduction."""

from __future__ import annotations


class InvestigationFailure(Exception):
    """Pipeline failure mapped onto the job lifecycle by the worker."""

    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class InvestigationAbort(Exception):
    """Cooperative cancellation: unwinds the pipeline without failing it."""

    pass


class InvestigationParked(Exception):
    """Human gate reached: the stage finished, the run pauses honestly."""

    def __init__(self, output: dict) -> None:
        super().__init__("Parked for human approval.")
        self.output = output
