"""Compatibility imports; implementation lives in application.projects."""
from .application.projects import validate_project_id, ProjectStore, DEFAULT_WORKSPACES, EXTERNAL_ID

__all__ = ['validate_project_id', 'ProjectStore', 'DEFAULT_WORKSPACES', 'EXTERNAL_ID']
