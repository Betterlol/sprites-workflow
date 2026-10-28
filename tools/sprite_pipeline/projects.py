"""Compatibility imports; implementation lives in application.projects."""

from .application.projects import DEFAULT_WORKSPACES, EXTERNAL_ID, ProjectStore, validate_project_id

__all__ = ["validate_project_id", "ProjectStore", "DEFAULT_WORKSPACES", "EXTERNAL_ID"]
