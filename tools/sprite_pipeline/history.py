"""Compatibility imports; implementation lives in storage.history."""

from .storage.history import VERSION_ID, HistoryConflictError, OperationNotStarted, ProjectHistory

__all__ = ["HistoryConflictError", "OperationNotStarted", "ProjectHistory", "VERSION_ID"]
