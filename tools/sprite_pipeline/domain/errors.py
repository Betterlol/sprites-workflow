"""Application failures with transport-independent meanings."""


class ConflictError(ValueError):
    """The on-disk project changed since the editor loaded it."""


class OperationCancelled(Exception):
    """A long operation was stopped at a safe item boundary."""


class ExportCancelled(OperationCancelled):
    """An export was stopped at a safe item boundary."""
