"""Compatibility imports; implementation lives in interfaces.pipeline_cli."""

from .interfaces.pipeline_cli import STAGES, execute, main

__all__ = ["main", "execute", "STAGES"]
