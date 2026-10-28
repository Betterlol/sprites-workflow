"""Compatibility imports; implementation lives in storage.locking."""
from .storage.locking import ProjectBusyError, ProjectLock, project_lock

__all__ = ['ProjectBusyError', 'ProjectLock', 'project_lock']
