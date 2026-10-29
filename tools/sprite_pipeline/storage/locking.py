"""Reentrant, process-wide project locks shared by the HTTP and CLI writers."""

from __future__ import annotations

import errno
import math
import os
import threading
import time
from pathlib import Path
from typing import BinaryIO

DEFAULT_LOCK_TIMEOUT = 10.0
LOCK_RETRY_INTERVAL = 0.05


class ProjectBusyError(ValueError):
    """The project stayed busy past the acquisition deadline."""


class ProjectLock:
    def __init__(self, config: Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT):
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Project lock timeout must be finite and nonnegative")
        self.path = config.parent / ".sprite-workbench.lock"
        self.timeout = timeout
        self.thread = threading.RLock()
        self.depth = 0
        self.handle = None

    def _busy_error(self) -> ProjectBusyError:
        return ProjectBusyError(
            f"工程正在由其他操作使用，已等待 {self.timeout:g} 秒仍未取得锁，"
            "请等待当前操作完成后重试。"
        )

    def _lock_once(self, handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _lock_until(self, handle: BinaryIO, deadline: float) -> None:
        while True:
            try:
                self._lock_once(handle)
                return
            except OSError as error:
                # Only lock contention is retried. Invalid handles, unsupported
                # operations and file-opening permission errors keep their cause.
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise self._busy_error() from error
                time.sleep(min(LOCK_RETRY_INTERVAL, remaining))

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        if not self.thread.acquire(timeout=self.timeout):
            raise self._busy_error()
        try:
            if self.depth == 0:
                handle = self.path.open("a+b")
                try:
                    self._lock_until(handle, deadline)
                    # Windows can lock a byte beyond EOF. Initialize only after
                    # acquisition so two first-time users cannot write a locked byte.
                    if os.fstat(handle.fileno()).st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                except BaseException:
                    handle.close()  # Also releases an OS lock if initialization failed.
                    raise
                self.handle = handle
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
