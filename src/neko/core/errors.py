"""Exception hierarchy. Every layer raises a subclass of NekoError so the
orchestrator can turn failures into honest, user-facing explanations."""

from __future__ import annotations


class NekoError(Exception):
    """Base class for all N.E.K.O. errors."""

    user_message: str = "Something went wrong."

    def __init__(self, message: str = "", *, user_message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        if user_message is not None:
            self.user_message = user_message


class ConfigError(NekoError):
    user_message = "The configuration is invalid."


class DatabaseError(NekoError):
    user_message = "The local database reported an error."


class ModelUnavailableError(NekoError):
    user_message = "No suitable model is available right now."


class ModelTimeoutError(NekoError):
    user_message = "The model took too long to respond."


class ResourceBudgetError(NekoError):
    user_message = "Not enough free memory or disk for this request."


class PermissionDeniedError(NekoError):
    user_message = "That action is not permitted by the current safety policy."


class ApprovalRequiredError(NekoError):
    user_message = "That action needs your approval first."


class ToolError(NekoError):
    user_message = "A tool failed."


class ToolValidationError(ToolError):
    user_message = "The tool was called with invalid arguments."


class CancelledError(NekoError):
    user_message = "The task was cancelled."


class PeripheralUnavailableError(NekoError):
    user_message = "A required device or optional component is not available."
