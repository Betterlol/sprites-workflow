"""Reentrant, process-wide project locks shared by the HTTP and CLI writers."""

from __future__ import annotations

import os
import threading
from pathlib import Path


class ProjectBusyError(ValueError):
    """Another process is reading or changing the project."""


class ProjectLock:
    def __init__(self, config: Path):
        self.path = config.parent / ".sprite-workbench.lock"
        self.thread = threading.RLock()
        self.depth = 0
        self.handle = None

    def __enter__(self):
        self.thread.acquire()
        try:
            if self.depth == 0:
                self.handle = self.path.open("a+b")
                if self.path.stat().st_size == 0:
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    self.handle.close()
                    self.handle = None
                    raise ProjectBusyError("工程正由其他进程使用，请稍后重试。") from error
            self.depth += 1
            return self
        except BaseException:
            self.thread.release()
            raise

    def __exit__(self, *args):
        try:
            self.depth -= 1
            if self.depth == 0:
                try:
                    self.handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                finally:
                    self.handle.close()
                    self.handle = None
        finally:
            self.thread.release()


_registry: dict[str, ProjectLock] = {}
_registry_lock = threading.Lock()


def project_lock(config: Path) -> ProjectLock:
    config = config.resolve()
    key = os.path.normcase(str(config))
    with _registry_lock:
        if key not in _registry:
            _registry[key] = ProjectLock(config)
        return _registry[key]
