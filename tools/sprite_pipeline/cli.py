"""Compatibility imports; implementation lives in interfaces.pipeline_cli."""
from .interfaces.pipeline_cli import main, execute, STAGES

__all__ = ['main', 'execute', 'STAGES']
